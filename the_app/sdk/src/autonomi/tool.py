"""
Tool primitive for the Autonomi SDK.

Tools are typed functions that agents can call. The @tool decorator
automatically generates JSON schemas from type hints.

Example:
    from autonomi import tool

    @tool
    def read_file(path: str) -> str:
        '''Read contents of a file.

        Args:
            path: Absolute path to the file

        Returns:
            File contents as string
        '''
        with open(path) as f:
            return f.read()
"""

import inspect
import json
from dataclasses import dataclass, field
from functools import wraps
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

T = TypeVar("T")


class ToolError(Exception):
    """Error raised when a tool execution fails."""

    def __init__(self, message: str, tool_name: str = "", recoverable: bool = True):
        self.message = message
        self.tool_name = tool_name
        self.recoverable = recoverable
        super().__init__(message)


@dataclass
class ToolResult:
    """Result of a tool execution."""
    success: bool
    output: Any
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, output: Any, **metadata: Any) -> "ToolResult":
        """Create a successful result."""
        return cls(success=True, output=output, metadata=metadata)

    @classmethod
    def fail(cls, error: str, **metadata: Any) -> "ToolResult":
        """Create a failed result."""
        return cls(success=False, output=None, error=error, metadata=metadata)


@dataclass
class Tool:
    """A tool that can be called by an agent."""
    name: str
    description: str
    function: Callable[..., Any]
    schema: Dict[str, Any]
    tags: List[str] = field(default_factory=list)
    requires_confirmation: bool = False

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with the given arguments."""
        try:
            result = self.function(**kwargs)
            # Handle async functions
            if inspect.iscoroutine(result):
                result = await result
            return ToolResult.ok(result)
        except ToolError as e:
            return ToolResult.fail(e.message)
        except Exception as e:
            return ToolResult.fail(str(e))

    def execute_sync(self, **kwargs: Any) -> ToolResult:
        """Execute the tool synchronously."""
        try:
            result = self.function(**kwargs)
            if inspect.iscoroutine(result):
                raise ToolError("Cannot execute async tool synchronously", self.name)
            return ToolResult.ok(result)
        except ToolError as e:
            return ToolResult.fail(e.message)
        except Exception as e:
            return ToolResult.fail(str(e))

    def to_openai_schema(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.schema,
            },
        }

    def to_anthropic_schema(self) -> Dict[str, Any]:
        """Convert to Anthropic tool use format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.schema,
        }


def _python_type_to_json_type(python_type: Any) -> Dict[str, Any]:
    """Convert a Python type hint to JSON Schema type."""
    origin = get_origin(python_type)
    args = get_args(python_type)

    # Handle None / NoneType
    if python_type is type(None):
        return {"type": "null"}

    # Handle basic types
    if python_type is str:
        return {"type": "string"}
    if python_type is int:
        return {"type": "integer"}
    if python_type is float:
        return {"type": "number"}
    if python_type is bool:
        return {"type": "boolean"}

    # Handle Optional[X] (Union[X, None])
    if origin is Union:
        non_none_args = [a for a in args if a is not type(None)]
        if len(non_none_args) == 1:
            # Optional[X]
            return _python_type_to_json_type(non_none_args[0])
        # Union of multiple types
        return {"anyOf": [_python_type_to_json_type(a) for a in non_none_args]}

    # Handle List[X]
    if origin is list:
        if args:
            return {"type": "array", "items": _python_type_to_json_type(args[0])}
        return {"type": "array"}

    # Handle Dict[K, V]
    if origin is dict:
        return {"type": "object"}

    # Handle Literal
    try:
        from typing import Literal
        if origin is Literal:
            return {"type": "string", "enum": list(args)}
    except ImportError:
        pass

    # Default to string for unknown types
    return {"type": "string"}


def _parse_docstring(docstring: Optional[str]) -> tuple[str, Dict[str, str]]:
    """Parse a docstring to extract description and parameter descriptions."""
    if not docstring:
        return "", {}

    lines = docstring.strip().split("\n")
    description_lines: List[str] = []
    param_descriptions: Dict[str, str] = {}
    current_param: Optional[str] = None
    in_args_section = False

    for line in lines:
        stripped = line.strip()

        # Check for Args: section
        if stripped.lower() in ("args:", "arguments:", "parameters:"):
            in_args_section = True
            continue

        # Check for Returns: or other sections
        if stripped.lower() in ("returns:", "return:", "raises:", "raises:", "example:", "examples:"):
            in_args_section = False
            current_param = None
            continue

        if in_args_section:
            # Check if this is a new parameter (name: description)
            if ":" in stripped and not stripped.startswith(" "):
                parts = stripped.split(":", 1)
                param_name = parts[0].strip()
                param_desc = parts[1].strip() if len(parts) > 1 else ""
                # Remove type annotations from param name
                param_name = param_name.split("(")[0].strip()
                current_param = param_name
                param_descriptions[param_name] = param_desc
            elif current_param and stripped:
                # Continuation of previous parameter description
                param_descriptions[current_param] += " " + stripped
        else:
            # Main description
            if stripped:
                description_lines.append(stripped)

    description = " ".join(description_lines)
    return description, param_descriptions


def _generate_schema(func: Callable[..., Any]) -> tuple[str, Dict[str, Any]]:
    """Generate JSON Schema from function signature and docstring."""
    sig = inspect.signature(func)
    type_hints = get_type_hints(func) if hasattr(func, "__annotations__") else {}
    docstring = func.__doc__

    # Parse docstring
    description, param_descriptions = _parse_docstring(docstring)

    # Build parameters schema
    properties: Dict[str, Any] = {}
    required: List[str] = []

    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue

        param_type = type_hints.get(name, str)
        param_schema = _python_type_to_json_type(param_type)

        # Add description from docstring
        if name in param_descriptions:
            param_schema["description"] = param_descriptions[name]

        properties[name] = param_schema

        # Check if required (no default value)
        if param.default is inspect.Parameter.empty:
            # Check if it's Optional
            origin = get_origin(param_type)
            args = get_args(param_type)
            is_optional = origin is Union and type(None) in args
            if not is_optional:
                required.append(name)

    schema: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required

    return description, schema


def tool(
    func: Optional[Callable[..., T]] = None,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    requires_confirmation: bool = False,
) -> Union[Tool, Callable[[Callable[..., T]], Tool]]:
    """
    Decorator to create a Tool from a function.

    Can be used with or without arguments:

        @tool
        def my_function(x: int) -> str:
            '''Description here.'''
            return str(x)

        @tool(name="custom_name", tags=["math"])
        def another_function(x: int) -> str:
            return str(x)

    Args:
        func: The function to wrap (when used without parentheses)
        name: Override the tool name (defaults to function name)
        description: Override the description (defaults to docstring)
        tags: Tags for tool discovery
        requires_confirmation: Whether to require user confirmation before execution

    Returns:
        A Tool instance
    """

    def decorator(fn: Callable[..., T]) -> Tool:
        auto_description, schema = _generate_schema(fn)

        return Tool(
            name=name or fn.__name__,
            description=description or auto_description or f"Execute {fn.__name__}",
            function=fn,
            schema=schema,
            tags=tags or [],
            requires_confirmation=requires_confirmation,
        )

    if func is not None:
        # Used without parentheses: @tool
        return decorator(func)

    # Used with parentheses: @tool() or @tool(name="x")
    return decorator


class ToolRegistry:
    """
    Registry for dynamic tool discovery.

    For large tool libraries, enables on-demand tool discovery
    instead of loading all tools into context.

    Example:
        registry = ToolRegistry()
        registry.register(read_file, tags=["filesystem", "read"])
        registry.register(write_file, tags=["filesystem", "write"])

        # Search for tools by tag
        fs_tools = registry.search(tags=["filesystem"])
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}
        self._by_tag: Dict[str, List[str]] = {}

    def register(
        self,
        tool_or_func: Union[Tool, Callable[..., Any]],
        tags: Optional[List[str]] = None,
    ) -> Tool:
        """Register a tool or function."""
        if isinstance(tool_or_func, Tool):
            t = tool_or_func
        else:
            t = tool(tool_or_func)

        # Merge tags
        all_tags = set(t.tags)
        if tags:
            all_tags.update(tags)
        t.tags = list(all_tags)

        self._tools[t.name] = t

        # Index by tags
        for tag in t.tags:
            if tag not in self._by_tag:
                self._by_tag[tag] = []
            if t.name not in self._by_tag[tag]:
                self._by_tag[tag].append(t.name)

        return t

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def search(
        self,
        tags: Optional[List[str]] = None,
        query: Optional[str] = None,
    ) -> List[Tool]:
        """Search for tools by tags or query."""
        results: List[Tool] = []

        if tags:
            # Find tools matching all tags
            matching_names: Optional[set[str]] = None
            for tag in tags:
                tag_tools = set(self._by_tag.get(tag, []))
                if matching_names is None:
                    matching_names = tag_tools
                else:
                    matching_names &= tag_tools

            if matching_names:
                results = [self._tools[n] for n in matching_names]

        elif query:
            # Simple substring search in name and description
            query_lower = query.lower()
            for t in self._tools.values():
                if query_lower in t.name.lower() or query_lower in t.description.lower():
                    results.append(t)
        else:
            results = list(self._tools.values())

        return results

    def all(self) -> List[Tool]:
        """Get all registered tools."""
        return list(self._tools.values())

    def search_tool(self) -> Tool:
        """
        Return a meta-tool that can search this registry.

        This allows agents to discover tools dynamically.
        """
        registry = self

        @tool(name="search_tools", tags=["meta"])
        def search_tools(query: str) -> str:
            """Search for available tools by keyword or capability.

            Args:
                query: What kind of tool you're looking for

            Returns:
                List of matching tools with their descriptions
            """
            tools = registry.search(query=query)
            if not tools:
                return "No matching tools found."

            lines = ["Available tools:"]
            for t in tools[:10]:  # Limit to 10 results
                lines.append(f"- {t.name}: {t.description}")
            return "\n".join(lines)

        return search_tools
