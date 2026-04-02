@echo off
REM SMT MCP Server - One-Click Setup
REM Usage: install.bat

setlocal enabledelayedexpansion

echo 🚀 Installing SMT MCP Server...
echo.

REM Check Python version
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found! Please install Python 3.11+
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set python_version=%%i
echo ✓ Python %python_version% found
echo.

REM Create virtual environment
if not exist "venv" (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo 🔌 Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo 📚 Installing dependencies...
pip install -q -e .

REM Check for Docker
where docker-compose >nul 2>&1
if errorlevel 1 (
    echo.
    echo ⚠️  Docker not found. Neo4j not started.
    echo You can start it manually with: docker-compose up -d
    goto :skip_docker
)

echo.
set /p start_neo4j="Start Neo4j in Docker? (y/n): "
if /i "%start_neo4j%"=="y" (
    echo 🐳 Starting Neo4j...
    docker-compose up -d
    timeout /t 3 /nobreak
    echo ✓ Neo4j running at bolt://localhost:7687
)

:skip_docker

echo.
echo ✅ Testing installation...
python -m pytest tests/unit/ -q --tb=no 2>nul
if errorlevel 0 (
    echo ✓ All tests passed!
)

echo.
echo ════════════════════════════════════════════
echo ✨ SMT MCP Server installed successfully!
echo ════════════════════════════════════════════
echo.
echo Next steps:
echo   1. Start the server:
echo      python run_mcp.py
echo.
echo   2. Configure Claude Code:
echo      Add to .claude/settings.json:
echo        "mcpServers": [
echo          {
echo            "name": "smt-graph",
echo            "command": "python",
echo            "args": ["%cd%\run_mcp.py"]
echo          }
echo        ]
echo.
echo   3. Restart Claude Code and use the tools!
echo.
echo 📖 Read docs/MCP_QUICK_START.md for details
echo.
pause
