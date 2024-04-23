#!/bin/env bash

poetry run getallspider --url=https://quotes.toscrape.com \
                        --allowed-domains=toscrape.com \
                        --save-dir=./scrapy-quotes-webdomain
