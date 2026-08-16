"""
Tests for the AST parser.
"""
import pytest
from app.intelligence.ast_parser import parse_file, FileAST


SAMPLE_PYTHON = '''
import os
from typing import Optional
from flask import request

class UserService:
    def get_user(self, user_id: str) -> Optional[dict]:
        """Fetch a user by ID."""
        query = f"SELECT * FROM users WHERE id = {user_id}"
        return self.db.execute(query)

    async def create_user(self, name: str, email: str) -> dict:
        result = self.db.insert(name, email)
        return result

def process_order(order_id: int, user_id):
    user_id = int(user_id)
    return {"order": order_id, "user": user_id}
'''


def test_parse_functions():
    ast = parse_file(SAMPLE_PYTHON, "test.py")
    assert isinstance(ast, FileAST)
    fn_names = [f.name for f in ast.functions]
    assert "get_user" in fn_names
    assert "create_user" in fn_names
    assert "process_order" in fn_names


def test_parse_classes():
    ast = parse_file(SAMPLE_PYTHON, "test.py")
    cls_names = [c.name for c in ast.classes]
    assert "UserService" in cls_names


def test_parse_imports():
    ast = parse_file(SAMPLE_PYTHON, "test.py")
    modules = [i.module for i in ast.imports]
    assert "os" in modules or any("os" in m for m in modules)


def test_async_function_detected():
    ast = parse_file(SAMPLE_PYTHON, "test.py")
    async_fns = [f for f in ast.functions if f.is_async]
    assert any(f.name == "create_user" for f in async_fns)


def test_empty_file():
    ast = parse_file("", "empty.py")
    assert ast.functions == []
    assert ast.classes == []
    assert ast.imports == []


def test_syntax_error_graceful():
    broken = "def broken(:\n    pass"
    ast = parse_file(broken, "broken.py")
    # Should not raise, may have empty results
    assert ast is not None


def test_function_parameters():
    ast = parse_file(SAMPLE_PYTHON, "test.py")
    fn = next((f for f in ast.functions if f.name == "process_order"), None)
    assert fn is not None
    assert "order_id" in fn.parameters or "user_id" in fn.parameters
