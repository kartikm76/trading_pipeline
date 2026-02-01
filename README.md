find . \( -path "./venv" -o -name "dist" -o -name ".git" \) -prune \
-o -type f \( -name "*.py" -o -name "*.sh" -o -name "*.yaml" -o -name "requirements.txt" \) \
-exec echo "--- FILE: {} ---" \; -exec cat {} \; > codebase_snapshot.txt

source venv/bin/activate
