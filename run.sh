#!/bin/bash
# A simple runner script for the new Workflow Engine.

# Check for .env file
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found. Please copy .env.example to .env and fill in your credentials."
    exit 1
fi

echo "Starting Streamlit Web UI for the Workflow Engine..."
# Using python -m with streamlit run ensures that the src directory is in the python path,
# solving all relative import issues cleanly.
python3 -m streamlit run src/app/streamlit_app.py