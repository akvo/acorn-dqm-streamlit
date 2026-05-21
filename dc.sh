#!/bin/bash

# dc.sh - Docker Compose Wrapper Script for Acorn DQM

# Exit immediately if a command exits with a non-zero status
set -e

# Help command
function show_help() {
    echo "Usage: ./dc.sh [command]"
    echo ""
    echo "Commands:"
    echo "  up             Start the application in the background (hot-reloading on port 8501)"
    echo "  up-build       Rebuild and start the application in the background"
    echo "  down           Stop the application and remove containers"
    echo "  restart        Restart the application containers"
    echo "  logs           Show logs for the running application"
    echo "  exec [cmd]     Execute an arbitrary command inside the running app container"
    echo "  ruff-check     Run Ruff code style and lint checks inside the container"
    echo "  ruff-format    Run Ruff code formatter inside the container"
    echo "  test           Run pytest unit tests inside the container"
    echo "  shell          Open an interactive shell inside the app container"
    echo "  help           Show this help message"
}

case "$1" in
    up)
        docker compose up -d
        echo "Application started! Access it at http://localhost:8080/?partner=COMACO"
        ;;
    up-build)
        docker compose up -d --build
        echo "Application rebuilt and started! Access it at http://localhost:8080/?partner=COMACO"
        ;;
    down)
        docker compose down
        echo "Application stopped."
        ;;
    restart)
        docker compose restart
        ;;
    logs)
        docker compose logs -f
        ;;
    exec)
        shift
        docker compose exec app "$@"
        ;;
    ruff-check)
        docker compose exec app ruff check
        ;;
    ruff-format)
        docker compose exec app ruff format
        ;;
    test)
        docker compose exec app pytest
        ;;
    shell)
        docker compose exec app /bin/bash
        ;;
    *)
        show_help
        ;;
esac
