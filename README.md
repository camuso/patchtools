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
|                      | scripts that use `#**` and `#*` as doc       |
|                      | delimiters.                                  |
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
| `mygitlab-mrs`       | Lists GitLab merge requests authored by you, |
|                      | filtered by state (merged, open, closed).    |
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
| `docscript`  | Extract documentation from scripts.             |
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

## Library Files (`lib/` directory)

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
|                             |                                          |
| `tmux.cherp.conf`           | Tmux configuration for wcherp.           |

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

## Deprecated Scripts (`deprecated/` directory)

These scripts are no longer actively maintained but are preserved
for reference.

| Script              | Description                                  |
|---------------------|----------------------------------------------|
| `gnice`             | Re-commits downstream commits inserting      |
|                     | JIRA, CVE, and upstream status info.         |
|                     |                                              |
| `prep-usb-backport` | Creates USB subsystem-specific commit logs   |
|                     | for backporting, with duplicate detection.   |
|                     |                                              |
| `wcherp`            | Tmux wrapper that spawns a split-screen      |
|                     | session for cherp with a tail view of the    |
|                     | backport commits file.                       |

---

## Installation

Add the patchtools directory to your PATH:

```bash
export PATH=$PATH:/path/to/patchtools
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
- Optional: tmux (for wcherp), sshfs (for sshmount)
- Optional: vimdiff, emacs, or tkdiff (for patcmp)
