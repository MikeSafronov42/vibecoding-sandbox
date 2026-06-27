FROM python:3.12-slim

ARG USER_UID=1007
ARG USER_GID=1006

# Create a non-root user matching the host UID/GID
RUN groupadd -g ${USER_GID} agent && \
    useradd -m -u ${USER_UID} -g ${USER_GID} agent

# Minimal system tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pre-install common Python packages so benign tasks don't need network for pip
RUN pip install --no-cache-dir \
    requests \
    beautifulsoup4 \
    pandas \
    jinja2

# Workspace and output owned by the agent user
RUN mkdir -p /workspace /output && chown agent:agent /workspace /output

USER agent
WORKDIR /workspace

CMD ["bash"]
