import argparse
import mimetypes
import os
import re
from pathlib import Path
from typing import Any
from typing import Iterable
from urllib.parse import urlparse

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

        # Remove charset of content type.
        file_ext = mimetypes.guess_extension(re.sub(pattern=";.*", repl="", string=content_type))
        url_parsed = urlparse(url)

        # Not exist file's extension for URL
        if not re.compile(pattern="/.+\\.[a-zA-Z0-9]{2,10}$").match(url_parsed.path) and not url_parsed.query:
            dir_path += os.sep.join(segs)
            filepath = dir_path + f"/index{file_ext}"
        # Exist at least a "query" into URL.
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
    parser.add_argument("--delay", dest="delay", type=int, default=1, help="delay in seconds between requests.")
    parser.add_argument("--randomize-delay", dest="randomize_delay", type=bool, default=True,
                        help="randomize delay interval.")
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
        "CONCURRENT_REQUESTS": args.requests_per_domain * 2,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": args.requests_per_domain,
        "DOWNLOAD_DELAY": args.delay,
        "RANDOMIZE_DOWNLOAD_DELAY": args.randomize_delay,
        "DEPTH_STATS_VERBOSE": True,
        "DOWNLOAD_MAXSIZE": 0,
        "REACTOR_THREADPOOL_MAXSIZE": 1024,
        "ROBOTSTXT_OBEY": False,
        "ROBOTSTXT_ENABLED": False,
        "SCHEDULER_DISK_QUEUE": "scrapy.squeues.PickleFifoDiskQueue",
        "SCHEDULER_MEMORY_QUEUE": "scrapy.squeues.FifoMemoryQueue",
        "SCRAPER_SLOT_MAX_ACTIVE_SIZE": 8_388_608,
        "REDIRECT_ENABLED": True,
        "REDIRECT_MAX_TIMES": 15,
        "RETRY_ENABLED": True,
        "RETRY_TIMES": 5,
        "DEFAULT_REQUEST_HEADERS": {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0"},
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
