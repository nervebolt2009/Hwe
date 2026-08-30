.PHONY: test check package

check:
	python3 -m compileall -q app tests
	bash -n run-termux.sh

test:
	python3 -m pytest -q

package: check
	mkdir -p dist
	rm -f dist/wearsic-server-v2.zip
	zip -qr dist/wearsic-server-v2.zip app requirements.txt .env.example .gitignore README.md run-termux.sh tests
