.PHONY: help daily test verify status paper-status paper-reset install clean pack
VERSION ?= 0.11.0
PY := ./.venv/bin/python

help:
	@echo "make daily        - 一键日跑"
	@echo "make test         - pytest"
	@echo "make verify       - 健康报告"
	@echo "make status       - 团队状态"
	@echo "make paper-status - paper 账户"
	@echo "make paper-reset  - 清 paper 账户"
	@echo "make install      - 创建 venv + pip"
	@echo "make pack         - 打包 tarball (VERSION=0.3.0)"

install:
	python3 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt pytest pytest-asyncio pysocks

daily:
	./daily.sh

test:
	$(PY) -m pytest tests/ -v

verify:
	$(PY) -m tools.verify --tickers 600519.SS,AAPL,000858.SZ --date $$(date +%F)

status:
	./manage.py status

paper-status:
	./manage.py paper-status

paper-reset:
	./manage.py paper-reset

clean:
	rm -rf .cache __pycache__ */__pycache__ */*/__pycache__ .pytest_cache

pack:
	cd .. && tar --exclude='stock-agents-team/.venv' \
	  --exclude='stock-agents-team/.git' --exclude='stock-agents-team/.cache' \
	  --exclude='stock-agents-team/__pycache__' --exclude='*/__pycache__' \
	  --exclude='stock-agents-team/data/paper' --exclude='stock-agents-team/data/batch_state' \
	  --exclude='stock-agents-team/data/price_watch' --exclude='stock-agents-team/reports' \
	  --exclude='stock-agents-team/.pytest_cache' \
	  -czf stockops-$(VERSION).tar.gz stock-agents-team
	@ls -lh ../stockops-$(VERSION).tar.gz
