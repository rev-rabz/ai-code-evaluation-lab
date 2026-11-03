"""Server-owned evaluation tasks and their trusted test cases."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TestCase:
    name: str
    args: list[Any]
    expected: Any


@dataclass(frozen=True)
class Task:
    task_id: str
    function_name: str
    test_cases: tuple[TestCase, ...]


TASKS: dict[str, Task] = {
    "python.add": Task(
        task_id="python.add",
        function_name="add",
        test_cases=(
            TestCase("positive numbers", [2, 3], 5),
            TestCase("negative numbers", [-4, -6], -10),
            TestCase("zero", [0, 9], 9),
            TestCase("mixed signs", [-3, 8], 5),
            TestCase("decimal numbers", [1.25, 2.5], 3.75),
        ),
    ),
}


def get_task(task_id: str) -> Task:
    try:
        task = TASKS[task_id]
    except KeyError as exc:
        raise ValueError(f"Unknown evaluation task: {task_id}") from exc
    if not task.test_cases:
        raise ValueError(f"Task has no registered test cases: {task_id}")
    return task
