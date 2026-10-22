FROM python:3.12-slim
COPY fake_codex.py /usr/local/bin/codex
COPY fake_dsh.py /usr/local/bin/dsh
COPY deepseek_runner.py /opt/sciharness/deepseek_production.py
COPY fake_deepseek.py /opt/sciharness/deepseek_runner.py
COPY dsh_runner.py /opt/sciharness/dsh_runner.py
COPY codex_runner.py /opt/sciharness/codex_runner.py
COPY assert_isolation.py /opt/sciharness/assert_isolation.py
RUN chmod 755 /usr/local/bin/codex /usr/local/bin/dsh
