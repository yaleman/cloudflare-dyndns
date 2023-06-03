FROM python:3.11-alpine

RUN mkdir -p /app/cloudflare_dyndns
ADD pyproject.toml /app/
COPY cloudflare_dyndns/* /app/cloudflare_dyndns
RUN python -m pip install /app
RUN rm -rf /app
RUN mkdir /data/
WORKDIR /data/

CMD ["cloudflare-dyndns"]
