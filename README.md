# Patchtools

A comprehensive collection of bash scripts for Linux kernel patch
management, backporting, and review.

## Main Scripts

| Script               | Description                                  |
|----------------------|----------------------------------------------|
| `basher`             | Creates an empty bash script template with   |
|                      | placeholders for help text, usage function,  |
|                      | and optional includes for UI and config.     |
|                      |                                              |
| `check-for-fixes`    | Checks a patch series directory against an   |
|                      | upstream repo to find any required fix       |
|                      | commits that may be missing.                 |
|                      |                                              |
| `docscript`          | Extracts and displays documentation from     |
|                      | scripts. Supports legacy `#**`/`#*` format   |
|                      | and shdoc format (`@description`, `@arg`,    |
|                      | `@exitcode`). Use `-s` for script headers,   |
|                      | `-v` for verbose output, `-f` for functions. |
|                      |                                              |
| `extup`              | Displays downstream commits alongside their  |
|                      | corresponding upstream commits with dates.   |
|                      |                                              |
| `filter-backportlog` | Filters indigenous commits from a backport   |
|                      | log file by marking already-backported       |
|                      | commits with a leading `#`.                  |
|                      |                                              |
| `funcprof`           | Finds function definitions and call sites    |
|                      | in a code tree. Supports Bash, C, Python,    |
|                      | Go, Rust, and JavaScript.                    |
|                      |                                              |
| `git-verify-diff`    | Compares two commits using `git range-diff`  |
|                      | to confirm semantic equivalence.             |
|                      |                                              |
| `gitfirst`           | Finds the git commit that first created a    |
|                      | specified file.                              |
|                      |                                              |
| `gitfor1pat`         | Generates a single patch from a specific     |
|                      | commit with formatting options.              |
|                      |                                              |
| `gitforpat`          | Generates a patch set from a commit          |
|                      | expression with cover letter and versioning. |
|                      |                                              |
| `gitlasttag`         | Simple wrapper for `git describe --tags`     |
|                      | to get the most recent tag.                  |
|                      |                                              |
| `gitlinehistory`     | Traces the history of specific lines, line   |
|                      | ranges, or functions in a file through git.  |
|                      |                                              |
| `gitnice`            | Enhanced `git log --oneline` with options    |
|                      | for dates, author, hash width, and more.     |
|                      |                                              |
| `gort`               | **Gort is an Omnimodal Revision Tool** -     |
|                      | comprehensive interactive tool for           |
|                      | automating backporting from upstream.        |
|                      |                                              |
| `inscmtinfo`         | Inserts a file (like bugzilla/brew info)     |
|                      | after the Subject line in each patch file.   |
|                      |                                              |
| `kmake`              | Builds and installs the Linux kernel with    |
|                      | options for sparse checking, config          |
|                      | creation, and verbosity.                     |
|                      |                                              |
| `missingfixes`       | Parses `missing_fixes` file from patchreview |
|                      | to find fixes made before a given tag.       |
|                      |                                              |
| `mkbackportlog`      | Creates a list of commits to be backported,  |
|                      | comparing with downstream to identify        |
|                      | already-backported commits.                  |
|                      |                                              |
| `mkmod`              | Builds kernel modules from a kernel tree,    |
|                      | with options for clean, prepare, sync,       |
|                      | and restore.                                 |
|                      |                                              |
| `mygitlab-mrs`       | Lists GitLab merge requests authored by you  |
|                      | with combinable filters: state (-so/-sm/-sc),|
|                      | project (-p), title regex (-r), date range   |
|                      | (-da/-db), and count mode (-c).              |
|                      |                                              |
| `oneup`              | Extracts the upstream commit hash from a     |
|                      | downstream (RHEL) commit's git log.          |
|                      |                                              |
| `patbatcmp`          | Compares patch files in two directories      |
|                      | pair by pair, detecting mismatches.          |
|                      |                                              |
| `patbatcmpmgr`       | Interactive menu wrapper for `patbatcmp`     |
|                      | with persistent settings and verbose output. |
|                      |                                              |
| `patchreview`        | Comprehensive tool for reviewing patches,    |
|                      | comparing with upstream, detecting           |
|                      | conflicts and missing fixes.                 |
|                      |                                              |
| `patcmp`             | Interactive diff tool for comparing patch    |
|                      | files using vimdiff, emacs, or tkdiff.       |
|                      |                                              |
| `ptpage`             | Pager for displaying large texts formatted   |
|                      | with color and text attributes.              |
|                      |                                              |
| `renpat`             | Renames patch files in a directory using     |
|                      | their Subject lines as filenames.            |
|                      |                                              |
| `sshmount`           | Wrapper for sshfs to mount remote            |
|                      | directories via SSH.                         |
|                      |                                              |
---

## Tool Categories

### Menu-Driven Interactive Tools

| Script          | Description                                  |
|-----------------|----------------------------------------------|
| `gort`          | Full-featured backporting automation with    |
|                 | session management and conflict resolution.  |
|                 |                                              |
| `patchreview`   | Thorough review of patches from MRs or any   |
|                 | two directories.                             |
|                 |                                              |
| `patbatcmpmgr`  | Menu wrapper for batch patch comparison.     |
|                 |                                              |
| `mkbackportlog` | Interactive mode for creating backport       |
|                 | commit lists.                                |

### Git Utilities

| Script           | Description                                 |
|------------------|---------------------------------------------|
| `gitnice`        | Enhanced one-line git log with flexible     |
|                  | formatting options.                         |
|                  |                                             |
| `gitfirst`       | Find the commit that created a file.        |
|                  |                                             |
| `gitforpat`      | Format patches from commit expressions.     |
|                  |                                             |
| `gitfor1pat`     | Format a single patch from a commit.        |
|                  |                                             |
| `gitlasttag`     | Get the most recent git tag.                |
|                  |                                             |
| `gitlinehistory` | Trace line/function history through git.    |
|                  |                                             |
| `git-verify-diff`| Verify semantic equivalence of commits.     |
|                  |                                             |
| `extup`          | Extract upstream commits from downstream    |
|                  | logs.                                       |
|                  |                                             |
| `oneup`          | Extract upstream hash from a downstream     |
|                  | commit.                                     |
|                  |                                             |
| `mygitlab-mrs`   | Query your GitLab MRs with combinable       |
|                  | filters for state, project, title, dates.   |

### Patch Comparison Tools

| Script         | Description                                   |
|----------------|-----------------------------------------------|
| `patbatcmp`    | Batch line-by-line patch comparison.          |
|                |                                               |
| `patbatcmpmgr` | Interactive manager for batch comparisons.    |
|                |                                               |
| `patcmp`       | Visual diff comparison with vimdiff, emacs,   |
|                | or tkdiff.                                    |

### Kernel Build Tools

| Script  | Description                                          |
|---------|------------------------------------------------------|
| `kmake` | Build and install Linux kernel.                      |
|         |                                                      |
| `mkmod` | Build and sync kernel modules.                       |

### Utility Scripts

| Script       | Description                                     |
|--------------|-------------------------------------------------|
| `basher`     | Generate bash script templates.                 |
|              |                                                 |
| `docscript`  | Extract documentation from scripts (legacy      |
|              | and shdoc formats, with script description).    |
|              |                                                 |
| `funcprof`   | Find function definitions and call sites.       |
|              |                                                 |
| `inscmtinfo` | Insert info into patch files.                   |
|              |                                                 |
| `renpat`     | Rename patch files by subject.                  |
|              |                                                 |
| `sshmount`   | Mount remote directories via SSH.               |
|              |                                                 |
| `ptpage`     | Color-aware text pager.                         |

---

## Library Files (`lib/` directory - submodule)

The `lib/` directory is a Git submodule pointing to
[shell-lib](https://gitlab.cee.redhat.com/tcamuso/shell-lib). This allows the
library files to be shared across multiple projects.

| File                        | Description                              |
|-----------------------------|------------------------------------------|
| `ui.source`                 | User interface abstractions (colors,     |
|                             | prompts, input handling).                |
|                             |                                          |
| `config-manager.source`     | Configuration file management functions. |
|                             |                                          |
| `cfgmgr.source`             | Alternative config manager               |
|                             | implementation.                          |
|                             |                                          |
| `gitutilities.source`       | Git operation abstractions.              |
|                             |                                          |
| `patch-common.source`       | Functions common to patch tools.         |
|                             |                                          |
| `patch-utils.source`        | Basic utilities for patch operations.    |
|                             |                                          |
| `patch-mrutilities.source`  | Merge request and lab utilities.         |
|                             |                                          |
| `keypress-support.source`   | Keyboard input handling.                 |
|                             |                                          |
| `patchtools-version.source` | Version information.                     |
|                             |                                          |
| `gort.conf`                 | Config template for gort.                |
|                             |                                          |
| `mkbackportlog.conf`        | Config template for mkbackportlog.       |
|                             |                                          |
| `patbatcmpmgr.conf`         | Config template for patbatcmpmgr.        |
|                             |                                          |
| `patchreview.conf`          | Config template for patchreview.         |

---

## Manual Pages (`man/` directory)

| File                       | Description                             |
|----------------------------|-----------------------------------------|
| `gort.pgman`               | Manual for gort.                        |
|                            |                                         |
| `mkbackportlog.pgman`      | Manual for mkbackportlog.               |
|                            |                                         |
| `patchreview.pgman`        | Manual for patchreview.                 |
|                            |                                         |
| `patchreview-config.pgman` | Configuration guide for patchreview.    |
|                            |                                         |
| `patchreview.txt`          | Text version of patchreview manual.     |
|                            |                                         |
| `patchreview-config.txt`   | Text version of config guide.           |

---

## Installation

Clone the repository with submodules:

```bash
git clone --recurse-submodules https://gitlab.cee.redhat.com/tcamuso/patchtools.git
```

Or if you already cloned without submodules:

```bash
cd patchtools
git submodule update --init
```

Add the patchtools directory to your PATH:

```bash
export PATH="$PATH:$HOME/patchtools"
```

Add this to your `.bashrc` for persistence:

```bash
if [[ ":$PATH:" != *":$HOME/patchtools:"* ]]; then
    export PATH="$PATH:$HOME/patchtools"
fi
```

### Switching from GitHub to Internal GitLab

If you previously cloned from GitHub, the simplest approach is to
remove your existing clone and start fresh:

```bash
rm -rf ~/patchtools
git clone --recurse-submodules git@gitlab.cee.redhat.com:tcamuso/patchtools.git
```

A GitHub mirror is available at https://github.com/camuso/patchtools
for times when internal GitLab is inaccessible.

### Using Older Versions

Starting with v14.0, the `lib/` directory is a Git submodule. To
checkout older versions (v13.x and earlier), use the `-f` flag:

```bash
git checkout -f v13.4
```

To return to the latest version:

```bash
git checkout master
git submodule update --init
```

## Usage

Most scripts provide help when invoked with `-h` or `--help`:

```bash
gort -h
mkbackportlog -h
patchreview -h
```

For menu-driven tools, simply run the script name to enter
interactive mode:

```bash
gort
patchreview
mkbackportlog
```

## Requirements

- Bash 4.0 or higher
- Git
- Standard Linux utilities (awk, sed, grep, etc.)
- Optional: jq and curl (for mygitlab-mrs)
- Optional: lab CLI tool (for mygitlab-mrs, auto-install offered)
- Optional: sshfs (for sshmount)
- Optional: vimdiff, emacs, or tkdiff (for patcmp)

---

## Documentation Convention

Scripts in this repository use a standardized documentation format:

### Script-Level Documentation

```bash
#!/bin/bash
#
# scriptname - Brief description of the script
#
# Longer description and usage information...
#
# Usage:
#   scriptname [options] arguments
```

### Function-Level Documentation (shdoc format)

```bash
# @description Brief description of what the function does
# @arg $1 string Description of first argument
# @arg $2 int Description of second argument
# @set varname type Description of global variable modified
# @stdout Description of output
# @exitcode 0 Success
# @exitcode 1 Error condition
funcname() {
    # function body
    return 0
}
```

### Viewing Documentation

Use `docscript` to view documentation:

```bash
docscript scriptname           # List functions (concise)
docscript -s scriptname        # Include script description
docscript -v scriptname        # Full documentation (verbose)
docscript -f funcname script   # Show specific function
```
