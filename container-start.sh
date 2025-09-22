# Create a new file called 'container-start.sh'
@"
#!/bin/bash
uvicorn backend.app:app --host 0.0.0.0 --port 8000
"@ | Out-File -Encoding ASCII container-start.sh

# Then in Dockerfile:
CMD ["./container-start.sh"]