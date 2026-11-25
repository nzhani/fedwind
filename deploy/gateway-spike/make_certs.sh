#!/usr/bin/env bash
# M0 spike (SITE_NETWORK_PLAN.md §11): every certificate and key the spike needs, in ./pki.
#
#   internal-ca   signs the SuperLink's TLS certificate (Fleet + Control API inside the server)
#   web-ca        stands in for the public CA (Let's Encrypt) of sites.fedwind.test
#   site-ca       FedWind site CA: signs each plant's client certificate; publishes the CRL
#   local-ca      each plant's own CA for the tunnel's local listener (the SuperNode trusts it)
#
#   site1 (konaev)  valid client cert + Flower key that will be registered
#   site2 (saran)   valid client cert + Flower key that is NOT registered
#   site3 (shymkent) client cert that is revoked in the CRL
#
# Plant private keys are generated "at the plant" in the real flow; here everything is local test data.
set -euo pipefail
cd "$(dirname "$0")"
rm -rf pki && mkdir -p pki && cd pki

ca() {  # ca <name> <cn>
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-384 -nodes -days 30 \
    -keyout "$1.key" -out "$1.crt" -subj "/CN=$2" \
    -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null
}
leaf() {  # leaf <name> <cn> <ca> <ext-file>
  openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-384 -nodes -keyout "$1.key" -out "$1.csr" -subj "/CN=$2" 2>/dev/null
  openssl x509 -req -in "$1.csr" -CA "$3.crt" -CAkey "$3.key" -CAcreateserial -days 30 -out "$1.crt" -extfile "$4" 2>/dev/null
  rm "$1.csr"
}

ca internal-ca "FedWind internal CA (spike)"
ca web-ca "Public CA stand-in (spike)"
ca site-ca "FedWind site CA (spike)"
ca local-ca "Plant local CA (spike)"

printf 'subjectAltName=DNS:superlink\nextendedKeyUsage=serverAuth\n' > srv-superlink.ext
printf 'subjectAltName=DNS:sites.fedwind.test\nextendedKeyUsage=serverAuth\n' > srv-gateway.ext
printf 'subjectAltName=DNS:tunnel,DNS:localhost\nextendedKeyUsage=serverAuth\n' > srv-tunnel.ext
printf 'extendedKeyUsage=clientAuth\n' > client.ext

leaf superlink superlink internal-ca srv-superlink.ext
leaf gateway sites.fedwind.test web-ca srv-gateway.ext
leaf tunnel tunnel local-ca srv-tunnel.ext
leaf site1 konaev site-ca client.ext
leaf site2 saran site-ca client.ext
leaf site3 shymkent site-ca client.ext

# CRL of the site CA, revoking site3
cat > site-ca.cnf <<'EOF'
[ ca ]
default_ca = site
[ site ]
database = site-ca.index
crlnumber = site-ca.crlnum
default_md = sha384
default_crl_days = 30
EOF
: > site-ca.index
echo 01 > site-ca.crlnum
openssl ca -config site-ca.cnf -keyfile site-ca.key -cert site-ca.crt -revoke site3.crt 2>/dev/null
openssl ca -config site-ca.cnf -keyfile site-ca.key -cert site-ca.crt -gencrl -out site-ca.crl 2>/dev/null

# Flower SuperNode keys (OpenSSH format, NIST P-384, as flwr 1.25 expects)
for s in site1 site2; do ssh-keygen -q -t ecdsa -b 384 -N "" -C "$s" -f "flower-$s"; done

rm -f *.ext *.srl
chmod 644 ./*   # test data only; real plant keys stay 0600 inside the plant's secrets volume
echo "PKI ready in $(pwd):"; ls
openssl crl -in site-ca.crl -noout -text | grep -A1 'Serial Number' | head -2
