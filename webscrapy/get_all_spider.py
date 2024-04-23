import argparse
import os
import re
from pathlib import Path
from typing import Any
from typing import Iterable

import scrapy
from scrapy import Request
from scrapy.crawler import CrawlerProcess
from scrapy.http import Response


class GetAllSpider(scrapy.Spider):
    name: str = "getallspider"
    save_dir: str = None
    domain: str = None
    override: bool = False

    CONTENT_TYPE_HTML: str = "text/html"
    SELECT_REF_XPATH: str = "//a/@href|//link/@href|//script/@src|//img/@src|//base/@href|//area/@href"
    IGNORE_LINKS_REGEX = "^(mailto|javascript|xmpp|urn|tel):|^#$|^#[^/]+$|^$"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.allowed_domains = getattr(self, "allowed-domains", None)
        if self.allowed_domains is not None:
            self.allowed_domains = self.allowed_domains.split(",")

        self.url = getattr(self, "url", None)
        if self.url is None:
            raise RuntimeError("URL is None!")

        self.override = getattr(self, "override", False)

        segs = self.segments(self.url)
        self.domain = segs[0]

        self.save_dir = getattr(self, "save-dir", None)
        if self.save_dir is None:
            self.save_dir = os.curdir + f"/{self.domain}"
        save_dir_path = Path(self.save_dir)
        save_dir_path.mkdir(parents=True, exist_ok=True, mode=0o777)

    def start_requests(self) -> Iterable[Request]:
        yield scrapy.Request(url=self.url, callback=self.parse)

    def segments(self, url: str) -> [str]:
        url_path: str = re.compile("^.+://|/$").sub(repl="", string=url)
        return re.split(pattern="/", string=url_path)

    def save(self, url: str, content_type: str, data: bytes) -> int:
        segs = self.segments(url)
        dir_path = self.save_dir + os.sep
        filename = re.compile(pattern="\\0").sub(repl="", string=segs[-1])[:255]
        filepath = None

        if (self.CONTENT_TYPE_HTML in content_type.lower()
                and not re.compile(pattern="\\.(html|xhtml|htm)$|.*\\?.+").match(filename)):
            dir_path += os.sep.join(segs)
            filepath = dir_path + "/index.html"
        else:
            dir_path += os.sep.join(segs[:-1])
            filepath = dir_path + os.sep + filename
        self.log(f"filepath: {filepath}")

        path = Path(dir_path)
        path.mkdir(parents=True, exist_ok=True, mode=0o777)

        try:
            path = Path(filepath)
            path.touch(mode=0o777, exist_ok=not self.override)
            amount = path.write_bytes(data)
            return amount
        except FileExistsError:
            self.log(f"file {filepath} exists!")
            return 0

    def parse(self, response: Response, **kwargs: Any):
        self.log(f"url: {response.url}")
        self.log(f"response.headers: {response.headers}")

        content_type: str = response.headers["content-type"].decode("ascii")
        self.save(response.url, content_type, response.body)

        if self.CONTENT_TYPE_HTML in content_type.lower():
            # <link rel="stylesheet" href="/static/bootstrap.min.css">
            # links = response.css("//a::attr(href)").getall()
            links = response.xpath(self.SELECT_REF_XPATH).getall()
            follows = list()
            for link in links:
                if not re.compile(pattern=self.IGNORE_LINKS_REGEX).match(link):
                    follows.append(link)
            self.log(f"follows: {follows}")
            yield from response.follow_all(urls=follows, callback=self.parse)
        else:
            return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", dest="url", type=str, help="Web domain to scrapy.")
    parser.add_argument("--allowed-domains", dest="allowed_domains", type=str, help="domains separated by commas.")
    parser.add_argument("--save-dir", dest="save_dir", type=str, help="Local directory to save files.")
    parser.add_argument("--override", dest="override", type=bool, help="Override saved files.")
    parser.add_argument("--enable-log-file", dest="enable_log_file", type=bool, default=False,
                        help="Enable log to file.")
    parser.add_argument("--log-filename", dest="log_filename", type=str, default="log.out", help="Name of log file.")
    parser.add_argument("--requests-per-domain", dest="requests_per_domain", type=int, default=1,
                        help="Amount simultaneous requests to the web domain.")
    args = parser.parse_args()

    process = CrawlerProcess({
        "CONCURRENT_REQUESTS_PER_DOMAIN": args.requests_per_domain,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": args.requests_per_domain,
        "USER_AGENT": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "DEPT_STATS": True,
        "LOG_ENABLED": True,
        "LOG_STDOUT": True,
        "LOG_FILE_APPEND": True,
        "LOG_LEVEL": "DEBUG",
        "LOG_FILE": args.log_filename if args.enable_log_file else None
    })
    process.crawl(GetAllSpider,
                  **{"url": args.url,
                     "allowed-domains": args.allowed_domains,
                     "save-dir": args.save_dir,
                     "override": args.override})
    process.start()


if __name__ == "__main__":
    main()
