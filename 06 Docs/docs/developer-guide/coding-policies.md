# Coding Policies

These policies apply to all new and modified code in the ZFS Utilities project.
They complement the project-specific [Conventions](conventions.md) with general
style and safety rules for Bash and Python.

---

## Bash

### Core Principles

A good Bash coding style emphasizes **readability, maintainability, and
reliability**.  The goal is to write scripts that are easy to understand, debug,
and extend — both for yourself and others.

Key foundational practices:

- **Use `set -euo pipefail`** at the start of scripts to enable strict error
  handling:
    - `set -e`: Exit immediately on any command failure.
    - `set -u`: Treat unset variables as errors.
    - `set -o pipefail`: Ensure pipelines fail if any component fails.
- **Prefer `[[ ]]` over `[ ]`** for conditionals — more reliable and supports
  pattern matching.
- **Use `$(...)` for command substitution**, never backticks, for better nesting
  and readability.
- **Quote variables** using `"${var}"` to prevent word splitting and globbing
  issues.

Start each script file with:

```bash
#!/usr/bin/bash
set -euo pipefail

source ~/bashinit
bashinit
```

This initializes basic runtime variables and sources commonly-used functions.

### File and Naming Conventions

- **Shebang**: Use `#!/usr/bin/bash` unless portability across systems is
  required, in which case `#!/usr/bin/env bash` is acceptable.
- **File extensions**: Do not use an extension.
- **Variable naming**: Use lowercase for local and global variables (`my_var`),
  uppercase for environment/exported variables (`PATH`, `LOG_LEVEL`), and avoid
  all-caps for user-defined non-exported variables.
- **Function naming**: Use lowercase with underscores: `start_server`,
  `cleanup_temp_files`.

### Error Handling, Safety, and Messaging

- **Direct errors and messages to `log_msg()`** (provided by `bashinit` for
  bash, or `backup_config.py` for Python). Each message should begin with a
  priority:

    ```
    DEBUG   VERB   INFO   WARN   FATAL
    ```

    `FATAL` has the greatest importance.

- **Check command exit codes** and handle failures gracefully.
- **Use traps** for cleanup on exit, especially when using temporary files:

    ```bash
    cleanup() {
        rm -f /tmp/myscript.tmp
    }
    trap cleanup EXIT
    ```

- Avoid `eval` unless absolutely necessary, due to security risks.

### Code Readability and Structure

- **Indent with 4 spaces**, never tabs.
- **Limit line length to 100 characters**.  Break long commands with backslashes:

    ```bash
    command --option1 value1 \
            --option2 value2 \
            --option3 value3
    ```

- **Format pipelines clearly**:

    ```bash
    command1 | \
    command2 | \
    command3
    ```

- Avoid regular expressions if possible.  If used, they may not exceed 10
  characters in length.
- Use **long option names** when clarity is needed:

    ```bash
    rm --recursive --force -- "${dir}"
    ```

### Functions and Modularity

- **Use functions** to group related logic and improve readability. However, all functions must have more than one calling site.
- **Declare variables as `local`** inside functions:

    ```bash
    greet() {
        local name="${1}"
        echo "Hello, ${name}"
    }
    ```

- Apply the **Single Responsibility Principle**: each function should do one
  thing.
- For complex conditions, create named functions:

    ```bash
    is_help_requested() {
        [[ "$1" == "-h" || "$1" == "--help" ]]
    }
    ```

- **Never exit a script or function directly** with either `return` or `exit`.
  Instead, use:

    ```bash
    source $mydir/bashreturn [return code]
    ```

    at the point where the script exits (not as a preparatory step at the
    beginning of the script).

### Commenting and Documentation

- **Start each script with a header comment**:

    ```bash
    #!/usr/bin/bash
    #
    # Script: backup_db
    # Description: Performs hot backups of Oracle databases
    # Usage: ./backup_db [target_dir]
    #     $1      First argument
    #     $2      Second argument ... etc.
    #     $var1   Global variable used by this script. List them all.
    # Returns: 0 on success, 1 on failure
    ```

    Give complete and accurate descriptions for each argument and global
    variable in the header.

- **Comment non-obvious logic**, not every line.
- **Document functions** with purpose, arguments, and outputs.

### Security and Best Practices

- **Never use `sudo` with output redirection** directly; use `tee`:

    ```bash
    # Wrong:
    # sudo echo "data" > /root/file

    # Correct:
    echo "data" | sudo tee /root/file > /dev/null
    ```

- **Avoid SUID/SGID scripts** due to inherent security flaws.
- **Prefer absolute or explicitly relative paths** (`./script.sh`,
  `${PWD}/data`).
- **Use `log_msg` instead of `echo`** (bash) or **`print()`** (Python) for
  consistent, portable output.

---

## Python

### Core Principles

The standard style guide for Python is
**[PEP 8](https://pep8.org/)**, which emphasizes **readability and
consistency**.  The core principle is that code is read far more often than it is
written.

Key foundational rules:

- **Indentation**: Use **4 spaces per level**, never tabs.
- **Line length**: Limit lines to **100 characters**.
- **Whitespace**: Avoid extraneous spaces inside parentheses, brackets, or
  around `=` in keyword arguments.
- **Imports**: Each on separate lines, grouped as: standard library, third-party,
  local modules. Use absolute over relative imports.

### Naming Conventions

- **Variables and functions**: `lowercase_with_underscores`
- **Constants**: `UPPERCASE_WITH_UNDERSCORES`
- **Classes**: `CapWords` (PascalCase)
- **Modules**: `short_lowercase_names` (underscores allowed)
- **Private members**: `_single_leading_underscore`
- **"Magic" methods**: `__double_underscores__`

Avoid single-letter names like `l`, `O`, `I` due to visual ambiguity.

### Code Layout and Structure

- **Blank lines**: Two before top-level functions/classes, one between methods.
- **Line continuation**: Prefer implicit continuation inside parentheses,
  brackets, or braces over backslashes.
- **Binary operators**: Break **before** the operator for readability:

    ```python
    total = (first_variable
             + second_variable
             - third_variable)
    ```

### Comments and Documentation

- **Regular expressions**: Avoid retular expressions when possible. All regular expressions longer than 10 characters must be profusely documented in the code comments.
- **Block comments**: Start with `# ` and explain intent, not code.
- **Inline comments**: Use sparingly, with at least two spaces before `#`.
  Briefly explain intent and non-obvious code.
- **Docstrings**: Use triple quotes (`"""`) for modules, classes, functions.
  Follow PEP 257:

    ```python
    def add(a, b):
        """Return the sum of a and b."""
        return a + b
    ```

### Logging

All Python modules import `log_msg` from `backup_config` and use it for all
output:

```python
from backup_config import log_msg

log_msg("INFO: backup started")
log_msg("WARN: something unexpected")
log_msg("DEBUG: variable =", value)
```

- Priority levels: `DEBUG` < `VERB` < `INFO` < `WARN` < `FATAL` < none
- Messages without a recognized `LEVEL:` prefix use the implied "(none)" level
  and are always displayed in the log viewers
- `log_msg` always emits every message; filtering is done by the GUI log viewers
- In the GUI, messages route to the info panel; in CLI mode they go to `stderr`
- Each line is prefixed with `file:line:` via `inspect`

### Programming Recommendations

- **Comparisons to `None`**: Use `is None` or `is not None`, not `==`.
- **Boolean checks**: Prefer `if x:` over `if x == True:`.
- **Function design**: Prefer explicit parameters over `*args` or `**kwargs`
  unless necessary.
- **Mutable defaults**: Avoid them:

    ```python
    # Wrong
    def append_to(item, target=[]):
        target.append(item)
        return target

    # Correct
    def append_to(item, target=None):
        if target is None:
            target = []
        target.append(item)
        return target
    ```
