```markdown
# SU Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill teaches you the core development patterns and conventions used in the SU Python repository. You'll learn about file naming, import/export styles, commit message conventions, and how to structure and run tests. The repository does not use a specific framework, so patterns are lightweight and Pythonic.

## Coding Conventions

### File Naming
- Use **camelCase** for filenames.
  - Example: `myModule.py`, `dataProcessor.py`

### Import Style
- Use **absolute imports** to reference modules.
  - Example:
    ```python
    import myModule
    from utils.helperFunctions import processData
    ```

### Export Style
- Use **default exports** (i.e., define main classes/functions at the module level).
  - Example:
    ```python
    # In dataProcessor.py
    class DataProcessor:
        ...
    ```

### Commit Messages
- Follow **conventional commit** style.
- Use the `fix` prefix for bug fixes.
  - Example:
    ```
    fix: correct data parsing in DataProcessor
    ```

## Workflows

### Fix a Bug
**Trigger:** When you need to correct a bug in the codebase  
**Command:** `/fix-bug`

1. Identify the bug and its location in the code.
2. Create a new branch for the fix.
3. Make the necessary code changes.
4. Write or update tests in `*.test.*` files to cover the fix.
5. Commit your changes using the `fix:` prefix.
   - Example: `fix: handle NoneType in processData`
6. Push your branch and open a pull request.

### Add a New Module
**Trigger:** When adding new functionality  
**Command:** `/add-module`

1. Create a new Python file using camelCase naming.
   - Example: `newFeature.py`
2. Implement your functionality, exporting the main class or function.
3. Use absolute imports for any dependencies.
4. Add or update tests in a corresponding `*.test.*` file.
5. Commit your changes with a descriptive message.
   - Example: `feat: add newFeature module`
6. Push and open a pull request.

## Testing Patterns

- Test files follow the `*.test.*` naming pattern.
  - Example: `dataProcessor.test.py`
- The testing framework is **unknown**, so check existing test files for structure.
- Place tests alongside or near the modules they test.
- Example test file:
  ```python
  # dataProcessor.test.py
  from dataProcessor import DataProcessor

  def test_process_data():
      dp = DataProcessor()
      assert dp.process([1, 2, 3]) == [2, 3, 4]
  ```

## Commands
| Command      | Purpose                                  |
|--------------|------------------------------------------|
| /fix-bug     | Start the workflow to fix a bug          |
| /add-module  | Add a new module to the codebase         |
```
