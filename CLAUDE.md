# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Turbo Sorter Pro v12.5 - A dual-interface image organization tool combining Streamlit (admin dashboard) and NiceGUI (gallery interface) for managing large image collections through time-sync matching, ID collision resolution, category-based sorting, and gallery tagging with pairing capabilities.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run Streamlit dashboard (port 8501)
streamlit run app.py --server.port=8501 --server.address=0.0.0.0

# Run NiceGUI gallery (port 8080)
python3 gallery_app.py

# Both services (container startup)
./start.sh

# Syntax check all Python files
python3 -m py_compile *.py
```

## Architecture

### Dual-Framework Design
- **Streamlit (app.py, port 8501)**: Administrative dashboard with 5 modular tabs for management workflows
- **NiceGUI (gallery_app.py, port 8080)**: Modern gallery interface for image tagging and pairing operations
- **Shared Backend**: Both UIs use `SorterEngine` (engine.py) and the same SQLite database

### Core Components

| File | Purpose |
|------|---------|
| `engine.py` | Static `SorterEngine` class - all DB operations, file handling, image compression |
| `gallery_app.py` | NiceGUI gallery with `AppState` class for centralized state management |
| `app.py` | Streamlit entry point, loads tab modules |
| `tab_*.py` | Independent tab modules for each workflow |

### Database
SQLite at `/app/sorter_database.db` with tables: profiles, folder_ids, categories, staging_area, processed_log, folder_tags, profile_categories, pairing_settings.

### Tab Workflows
1. **Time-Sync Discovery** - Match images by timestamp across folders
2. **ID Review** - Resolve ID collisions between target/control folders
3. **Unused Archive** - Manage rejected image pairs
4. **Category Sorter** - One-to-many categorization
5. **Gallery Staged** - Grid-based tagging with Gallery/Pairing dual modes

## Key Patterns

- **ID Format**: `id001_`, `id002_` (zero-padded 3-digit prefix)
- **Staging Pattern**: Two-phase commit (stage → commit) with undo support
- **Image Formats**: .jpg, .jpeg, .png, .webp, .bmp, .tiff
- **Compression**: WebP with ThreadPoolExecutor (8 workers)
- **Permissions**: chmod 0o777 applied to committed files
- **Default Paths**: `/storage` when not configured
