# rhel2bootc tool image. Run with host root mounted at /host.
FROM registry.access.redhat.com/ubi9/ubi-minimal:9

RUN microdnf install -y python3.11 python3-pip && microdnf clean all

WORKDIR /app
COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir -e .

ENTRYPOINT ["rhel2bootc"]
CMD ["--help"]
