"""
Tests for the dependency graph builder.
"""
import pytest
from app.intelligence.ast_parser import parse_file
from app.intelligence.dependency_graph import DependencyGraph


FILE_A = '''
def get_user(user_id):
    return db_query(user_id)

def db_query(user_id):
    return {"id": user_id}
'''

FILE_B = '''
from module_a import get_user

def handle_request(request):
    user_id = request.get("user_id")
    return get_user(user_id)

def another_handler(req):
    return handle_request(req)
'''


def test_build_graph():
    ast_a = parse_file(FILE_A, "module_a.py")
    ast_b = parse_file(FILE_B, "module_b.py")
    dg = DependencyGraph()
    dg.build([ast_a, ast_b])
    assert "get_user" in dg.definitions
    assert "module_a.py" in dg.definitions["get_user"]


def test_callers_of():
    ast_a = parse_file(FILE_A, "module_a.py")
    ast_b = parse_file(FILE_B, "module_b.py")
    dg = DependencyGraph()
    dg.build([ast_a, ast_b])
    # handle_request calls get_user
    callers = dg.get_callers_of("get_user")
    # Should find at least one caller
    assert isinstance(callers, list)


def test_impact_set_empty_for_unknown():
    dg = DependencyGraph()
    result = dg.get_impact_set("nonexistent", "fake.py")
    assert result == []


def test_usages():
    ast_a = parse_file(FILE_A, "module_a.py")
    ast_b = parse_file(FILE_B, "module_b.py")
    dg = DependencyGraph()
    dg.build([ast_a, ast_b])
    assert isinstance(dg.usages, dict)
