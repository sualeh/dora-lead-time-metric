# GitHub Copilot Instructions

This document serves as a guide for GitHub Copilot when generating code for this project.

## General Guidelines

- Python code should adhere to PEP 8 style guidelines
- Maximum line length is 80 characters
- Use spaces for indentation (4 spaces for Python files)
- Ensure all files end with a newline
- Remove trailing whitespace from all lines

## Documentation

### Google Style Docstrings

Use Google style formatting for docstrings:

```python
def function_name(param1, param2):
    """Short description of what the function does.

    More detailed description if needed that can span
    multiple lines.

    Args:
        param1: Description of param1
        param2: Description of param2

    Returns:
        Description of return value

    Raises:
        KeyError: If a required key is not found
        ValueError: If an input cannot be processed
    """
    # Function body
```

### Class Docstrings

```python
class ClassName:
    """Summary of class purpose.

    More detailed class description that can span
    multiple lines.

    Attributes:
        attr1: Description of attr1
        attr2: Description of attr2
    """
    # Class body
```

## Code Style

- Use meaningful variable and function names
- Include type hints where appropriate
- Use f-strings only for simple string formatting in non-logging scenarios
- Follow the project's `.editorconfig` rules

## Jupyter Notebooks

- Include descriptive markdown cells before code cells
- Keep code cells focused on a single task
- Use appropriate section headers for organization

## Logging

### Use Lazy Logging with Placeholders

Instead of using f-strings for logging which evaluate expressions regardless of log level:

```python
# Don't do this
logging.debug(f"Processing item {item.id} with properties {item.get_properties()}")
```

Use placeholder style logging which only evaluates if the log level is enabled:

```python
# Do this instead
logging.debug("Processing item %s with properties %s", item.id, item.get_properties())
```

Or with more modern formatting:

```python
logging.debug("Processing item {} with properties {}", item.id, item.get_properties())
```

## Error Handling

- Use specific exception types rather than generic ones
- Always include descriptive error messages
- Consider using context managers for resource cleanup

## Testing

- Write tests for new functionality
- Follow the existing test patterns in the project
- Ensure tests are isolated and don't depend on external resources
