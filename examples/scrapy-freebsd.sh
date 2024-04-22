#!/usr/bin/zsh

poetry run getallspider --url=https://freebsdfoundation.org/our-work/journal/browser-based-edition --allowed-domains=freebsd.org,freebsdfoundation.org --save-dir=./scrapy-freebsd-webdomain
