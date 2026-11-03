import base64
import json
import docker
import pytest
from runner.engine import DockerExecutionEngine, ExecutionError


def result_log(stdout=b"ok", stderr=b"", tests=None):
    payload={"stdout":base64.b64encode(stdout).decode(),"stderr":base64.b64encode(stderr).decode(),"test_results":tests or []}
    return ("__EVAL_RESULT__"+json.dumps(payload)).encode()

class FakeContainer:
    def __init__(self, logs=None, polls_until_exit=1, exit_code=0, start_error=None):
        self.logs_payload=logs or result_log(tests=[{"name":"case","passed":True,"expected":1,"actual":1}])
        self.polls_until_exit=polls_until_exit; self.exit_code=exit_code; self.start_error=start_error
        self.attrs={"State":{"Status":"created","ExitCode":0}}; self.reload_calls=0
        self.started=False; self.removed=False; self.killed=False
    def start(self):
        if self.start_error: raise self.start_error
        self.started=True; self.attrs["State"]["Status"]="running"
    def reload(self):
        self.reload_calls+=1
        if self.polls_until_exit is not None and self.reload_calls>=self.polls_until_exit:
            self.attrs["State"].update(Status="exited",ExitCode=self.exit_code)
    def wait(self,timeout): return {"StatusCode":self.exit_code}
    def kill(self): self.killed=True; self.attrs["State"]["Status"]="exited"
    def logs(self,stdout,stderr): return self.logs_payload
    def remove(self,force): self.removed=True
class FakeContainers:
    def __init__(self,c): self.c=c; self.options=None
    def create(self,image,**kwargs): self.options={"image":image,**kwargs}; return self.c
class FakeClient:
    def __init__(self,c): self.containers=FakeContainers(c)
def make_engine(monkeypatch,c):
    client=FakeClient(c); monkeypatch.setattr(docker,"from_env",lambda:client)
    return DockerExecutionEngine(),client


def test_engine_runs_with_restricted_container_and_includes_trusted_suite(monkeypatch):
    c=FakeContainer(); engine,client=make_engine(monkeypatch,c)
    result=engine.execute("def add(a,b): return a+b",function_name="add",test_cases=[{"name":"one","args":[1,2],"expected":3}])
    opts=client.containers.options
    assert opts["network_disabled"] and opts["read_only"]
    assert opts["user"]=="65534:65534"
    assert "EVAL_TESTS_B64" in opts["environment"]
    assert result["test_results"][0]["passed"] is True
    assert c.removed


def test_timeout_kills_and_removes_container(monkeypatch):
    c=FakeContainer(polls_until_exit=None); engine,_=make_engine(monkeypatch,c)
    engine.timeout_seconds=0.01; engine.poll_interval_seconds=0.01
    result=engine.execute("while True: pass",function_name="add",test_cases=[{"name":"one","args":[1,2],"expected":3}])
    assert result["timed_out"] and c.killed and c.removed


def test_start_failure_still_removes_container(monkeypatch):
    c=FakeContainer(start_error=docker.errors.DockerException("failed")); engine,_=make_engine(monkeypatch,c)
    with pytest.raises(ExecutionError):
        engine.execute("pass",function_name="add",test_cases=[{"name":"one","args":[],"expected":None}])
    assert c.removed
