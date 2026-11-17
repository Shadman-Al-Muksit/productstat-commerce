FROM postgres:17-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-psycopg gnupg && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
COPY scripts/backup.py scripts/verify_restore.py /workspace/scripts/
ENTRYPOINT ["python3"]
CMD ["scripts/backup.py"]
