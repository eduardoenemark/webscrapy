import argparse
import logging
import mimetypes
import os
import re
from pathlib import Path
from typing import Any
from typing import Iterable
from urllib.parse import urlparse

from scrapy import Request, Spider
from scrapy.crawler import CrawlerProcess
from scrapy.http import Response
import logging


class GetAllSpider(Spider):
    name: str = "getallspider"
    save_dir: str = None
    domain: str = None
    override: bool = False
    only_links: bool = False
    also_save_links: bool = False
    regex_allowed_urls: str = None

    CONTENT_TYPE_HTML: str = "text/html"
    SELECT_REF_XPATH: str = "//a/@href|//link/@href|//script/@src|//img/@src|//base/@href|//area/@href"
    REGEX_IGNORE_LINKS = r"^(mailto|javascript|xmpp|urn|tel):|^#$|^#[^/]+$|^$"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.allowed_domains = getattr(self, "allowed-domains", None)
        if self.allowed_domains is not None:
            self.allowed_domains = self.allowed_domains.split(",")

        if self.regex_allowed_urls is None:
            self.regex_allowed_urls = r".*"

        self.compiled_regex_ignore_link = re.compile(pattern=self.REGEX_IGNORE_LINKS)
        self.compiled_regex_allowed_urls = re.compile(pattern=fr"{self.regex_allowed_urls}")

        self.url = getattr(self, "url", None)
        if self.url is None:
            raise RuntimeError("URL is None!")

        self.override = getattr(self, "override", False)
        self.only_links = getattr(self, "only-links", False)
        self.also_save_links = getattr(self, "also-save-links", False)

        parsed_url = urlparse(self.url)
        self.domain = parsed_url.hostname

        self.save_dir = getattr(self, "save-dir", None)
        if self.save_dir is None:
            self.save_dir = os.curdir + f"/{self.domain}"

        if not self.only_links or self.also_save_links:
            save_dir_path = Path(self.save_dir)
            save_dir_path.mkdir(parents=True, exist_ok=True, mode=0o777)

    def start_requests(self) -> Iterable[Request]:
        yield Request(url=self.url, callback=self.parse)

    def segments(self, url: str) -> [str]:
        url_path: str = re.compile(r"^.+://|/$").sub(repl="", string=url)
        return re.split(pattern="/", string=url_path)

    def create_physical_path(self, url: str, content_type: str) -> Path:
        segs = self.segments(url)
        dir_path = self.save_dir + os.sep
        filename = re.compile(pattern=r"\\0").sub(repl="", string=segs[-1])[:255]
        filepath = None

        # Remove charset of content type.
        file_ext = mimetypes.guess_extension(re.sub(pattern=";.*", repl="", string=content_type))
        parsed_url = urlparse(url)

        # Not exist file's extension for URL
        if not re.compile(pattern=r"/.+\\.[a-zA-Z0-9]{2,10}$").match(parsed_url.path) and not parsed_url.query:
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
            return path
        except FileExistsError as error:
            self.log(f"file {filepath} exists!")
            raise error

    def save_file(self, url: str, content_type: str, data: bytes):
        try:
            path = self.create_physical_path(url, content_type)
            file = open(file=f"{str(path.absolute())}", mode='wb')
            file.write(data)
            file.close()
        except Exception as ex:
            raise ex

    def save_link(self, url: str):
        fin = open(file=f"{self.domain}-links.txt", mode="at", encoding='utf8')
        fin.write(f"{url}\n")
        fin.close()

    def parse(self, response: Response, **kwargs: Any):
        self.log(f"headers=[{response.headers}], url=[{response.url}]")
        content_type: str = response.headers["content-type"].decode("ascii")

        try:
            if self.only_links or self.also_save_links:
                self.save_link(response.url)

            if not self.only_links or self.also_save_links:
                self.save_file(response.url, content_type, response.body)
        except Exception as ex:
            self.log(ex, logging.ERROR)

        if self.CONTENT_TYPE_HTML in content_type.lower():
            try:
                links = response.xpath(self.SELECT_REF_XPATH).getall()
                follows = list()
                for link in links:
                    if self.compiled_regex_ignore_link.match(link):
                        continue

                    parsed_url = urlparse(url=link)
                    if parsed_url.hostname is None:
                        link = response.urljoin(link)

                    if self.compiled_regex_allowed_urls.match(link):
                        follows.append(link)

                self.log(f"follows: {follows}")
                yield from response.follow_all(urls=follows, callback=self.parse)
            except Exception as error:
                self.log(error, level=logging.ERROR)
        else:
            return None


def main():
    DOMAIN_LOG_OPTION_VALUE = "[domain].log"
    logging.getLogger().addHandler(logging.StreamHandler())
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", dest="url", type=str, help="Web domain to scrapy.")
    parser.add_argument("--allowed-domains", dest="allowed_domains", type=str, help="Domains separated by commas.")
    parser.add_argument("--regex-allowed-urls", dest="regex_allowed_urls", type=str,
                        help="Regular expression of allowed URLs.")
    parser.add_argument("--delay", dest="delay", type=int, default=1, help="delay in seconds between requests.")
    parser.add_argument("--randomize-delay", dest="randomize_delay", type=bool, default=True,
                        help="randomize delay interval.")
    parser.add_argument("--save-dir", dest="save_dir", type=str, help="Local directory to save files.")
    parser.add_argument("--override", dest="override", type=bool, help="Override saved files.")
    parser.add_argument("--enable-log-file", dest="enable_log_file", type=bool, default=False,
                        help="Enable log to file.")
    parser.add_argument("--log-filename", dest="log_filename", type=str, default=DOMAIN_LOG_OPTION_VALUE,
                        help="Name of log file.")
    parser.add_argument("--requests-per-domain", dest="requests_per_domain", type=int, default=1,
                        help="Amount simultaneous requests to the web domain.")
    parser.add_argument("--only-links", dest="only_links", type=bool, default=False, help="Only save page links.")
    parser.add_argument("--also-save-links", dest="also_save_links", type=bool, default=False,
                        help="Also save page links.")
    args = parser.parse_args()

    log_filename = None
    if args.enable_log_file and args.log_filename == DOMAIN_LOG_OPTION_VALUE:
        parsed_url = urlparse(args.url)
        log_filename = f"./{parsed_url.hostname}.log"
    elif not args.enable_log_file:
        args.log_filename = None
    else:
        log_filename = args.log_filename

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
            "Accept-Language": "*",
            "Accept-Encoding": "gzip, deflate,*/*",
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
        "LOG_FILE": log_filename
    })
    process.crawl(GetAllSpider,
                  **{"url": args.url,
                     "allowed-domains": args.allowed_domains,
                     "regex_allowed_urls": args.regex_allowed_urls,
                     "save-dir": args.save_dir,
                     "only-links": args.only_links,
                     "also-save-links": args.also_save_links,
                     "override": args.override})
    process.start()


if __name__ == "__main__":
    main()
