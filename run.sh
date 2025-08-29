#!/bin/bash

# This script ensures the environment is clean before starting the bot.

echo "--- Cleaning up project caches... ---"
# Run the Python cleanup script using Poetry's virtual environment
poetry run python cleanup.py

echo "--- Starting the bot... ---"
# Run the main bot application
poetry run python -m bot.main
