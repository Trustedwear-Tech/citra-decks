FROM python:3.11-slim

# Create non-root user for execution
RUN groupadd -r sandbox && useradd -r -g sandbox -d /workspace -s /sbin/nologin sandbox

# Pre-install common data processing libraries
RUN pip install --no-cache-dir \
    pandas==2.2.3 \
    openpyxl==3.1.5 \
    xlrd==2.0.1 \
    python-docx==1.1.2 \
    Pillow==11.1.0 \
    xlsxwriter==3.2.0 \
    jsonschema==4.23.0 \
    python-pptx==1.0.2 \
    reportlab==4.2.5 \
    pdfplumber==0.11.4

# Create workspace directories
RUN mkdir -p /workspace/input /workspace/output && \
    chown -R sandbox:sandbox /workspace

# Switch to non-root user
USER sandbox
WORKDIR /workspace

# Default command: run a script passed as argument
ENTRYPOINT ["python", "/workspace/script.py"]
