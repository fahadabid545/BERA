"""Makes the certificate Cloudflare shows to our server (Authenticated Origin Pulls), our own, not
Cloudflare's shared one. The shared one is accepted for every Cloudflare customer, so another
customer's account could still reach this server. Ours is accepted only for the one we upload.

    python origin_pull_certificate.py create --env production --out FOLDER [--dry-run]
    python origin_pull_certificate.py check --folder FOLDER

`create` makes, for ONE environment (staging and production never share one):
    <env>-origin-pull-ca.pem   public: nginx trusts only this (ssl_client_certificate)
    <env>-client.pem           public: upload to Cloudflare
    <env>-client.key           SECRET: upload to Cloudflare, then DELETE it from the server
The private key of the little certificate authority is never saved, so nobody can make more
client certificates from it. To renew, create again, upload the new pair and put the new
authority file in place; nginx is reloaded in between.
"""

import argparse
import datetime
import os
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from harden_common import HardeningError, main_wrapper

ENVIRONMENTS = ("staging", "production")
VALID_DAYS = 730
WARN_DAYS = 60
KEY_BITS = 2048


def _name(common_name):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _validity(builder):
    now = datetime.datetime.now(datetime.UTC)
    return builder.not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(
        now + datetime.timedelta(days=VALID_DAYS)
    )


def make_pair(env):
    """(authority certificate, client certificate, client private key) as PEM bytes."""
    authority_key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_BITS)
    client_key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_BITS)
    authority_name = _name(f"Bera {env} origin pull authority")
    authority = (
        _validity(x509.CertificateBuilder())
        .subject_name(authority_name)
        .issuer_name(authority_name)
        .public_key(authority_key.public_key())
        .serial_number(x509.random_serial_number())
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(authority_key, hashes.SHA256())
    )
    client = (
        _validity(x509.CertificateBuilder())
        .subject_name(_name(f"Bera {env} Cloudflare origin pull"))
        .issuer_name(authority_name)
        .public_key(client_key.public_key())
        .serial_number(x509.random_serial_number())
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
        .sign(authority_key, hashes.SHA256())
    )  # authority_key goes out of scope here and is never written anywhere
    pem = serialization.Encoding.PEM
    return (
        authority.public_bytes(pem),
        client.public_bytes(pem),
        client_key.private_bytes(
            pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ),
    )


def _write_new(path, content, mode):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)


def create(arguments):
    folder = arguments.out
    names = {
        "authority": folder / f"{arguments.env}-origin-pull-ca.pem",
        "client": folder / f"{arguments.env}-client.pem",
        "key": folder / f"{arguments.env}-client.key",
    }
    print(f"{'would create' if arguments.dry_run else 'creating'} for {arguments.env}:")
    for path in names.values():
        print(f"  {path}")
    clashes = [path for path in names.values() if path.exists()]
    if clashes:
        raise HardeningError("A file already exists there; nothing was overwritten.")
    if arguments.dry_run:
        print("Dry run: nothing was created.")
        return 0
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    authority, client, key = make_pair(arguments.env)
    _write_new(names["authority"], authority, 0o644)
    _write_new(names["client"], client, 0o644)
    _write_new(names["key"], key, 0o600)
    print(
        f"Upload {names['client'].name} and {names['key'].name} to Cloudflare, "
        "then delete the .key file."
    )
    return 0


def days_left(certificate_file):
    certificate = x509.load_pem_x509_certificate(Path(certificate_file).read_bytes())
    return (certificate.not_valid_after_utc - datetime.datetime.now(datetime.UTC)).days


def check(arguments):
    """1 when a certificate is close to expiring, expired, or missing."""
    status = 0
    for env in ENVIRONMENTS:
        for name in (f"{env}-origin-pull-ca.pem", f"{env}-client.pem"):
            path = arguments.folder / name
            try:
                left = days_left(path)
            except (OSError, ValueError):
                print(f"{name}: not found or not readable")
                status = 1
                continue
            if left < WARN_DAYS:
                status = 1
            print(f"{name}: {left} days left{'  RENEW SOON' if left < WARN_DAYS else ''}")
    return status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("create", "check"))
    parser.add_argument("--env", choices=ENVIRONMENTS)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--folder", type=Path, help="check: where the .pem files are")
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.command == "create" and not (arguments.env and arguments.out):
        parser.error("create needs --env and --out")
    if arguments.command == "check" and not arguments.folder:
        parser.error("check needs --folder")
    commands = {"create": create, "check": check}
    return main_wrapper(lambda: commands[arguments.command](arguments)) or 0


if __name__ == "__main__":
    raise SystemExit(main())
