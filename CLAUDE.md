# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Turbo Sorter Pro v12.5** - A Python-based image management and sorting system with two web interfaces:
- **Streamlit app** (port 8501): 5-tab workflow for image discovery, collision resolution, archive management, categorization, and gallery staging
- **NiceGUI app** (port 8080): Real-time image tagging interface with hotkey support and batch operations

## Running the Applications

```bash
# Install dependencies
pip install -r requirements.txt

# Run Streamlit interface
streamlit run app.py --server.port=8501 --server.address=0.0.0.0

# Run NiceGUI gallery interface
python3 gallery_app.py

# Run both (Docker production mode)
./start.sh
```

## Architecture

### Core Components

- **`engine.py`** - `SorterEngine` class with 40+ static methods for all business logic. Central SQLite-based state management at `/app/sorter_database.db`. Handles profile management, image operations, staging, batch processing, and undo history.

- **`app.py`** - Streamlit entry point. Initializes database, manages session state, renders 5-tab interface.

- **`gallery_app.py`** - NiceGUI entry point with `AppState` class. Provides async image serving via FastAPI, hotkey-based tagging, and batch copy/move operations.

### Streamlit Tab Modules

| Tab | Module | Purpose |
|-----|--------|---------|
| 1. Discovery | `tab_time_discovery.py` | Time-sync matcher for sibling folders |
| 2. ID Review | `tab_id_review.py` | Collision detection and ID harmonization |
| 3. Unused | `tab_unused_review.py` | Archive review and restoration |
| 4. Category Sorter | `tab_category_sorter.py` | Bulk categorization and renaming |
| 5. Gallery Staged | `tab_gallery_sorter.py` | Interactive tagging interface |

### Database Schema (SQLite)

Key tables:
- `profiles` - Workspace configurations with tab path mappings
- `folder_ids` - Persistent folder identifiers
- `staging_area` - Pending file operations
- `processed_log` - Action history for undo
- `folder_tags` - Per-folder image tags with metadata
- `profile_categories` - Profile-specific category lists

### Key Patterns

- **Profile-based multi-tenancy**: Each workspace has isolated path configurations
- **Soft deletes**: Files moved to `_DELETED` folder for undo support
- **Parallel image loading**: `ThreadPoolExecutor` in `load_batch_parallel()`
- **Session state**: Streamlit `st.session_state` for tab indices and history
- **WebP compression**: PIL-based with configurable quality slider
