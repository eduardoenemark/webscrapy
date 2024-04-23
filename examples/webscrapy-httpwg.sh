#!/bin/env bash

poetry run getallspider --url=https://httpwg.org/specs/rfc7540.html \
                        --allowed-domains=httpwg.org
