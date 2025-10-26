#!/usr/bin/env python3
"""
TrackNote License Manager - Multi-Computer Support
==================================================

Commands:
  --generate-keys                           Generate Ed25519 keypair (first time only)
  --new-customer <name> <computers> <tier>  Create license package
  --add-fingerprint <package> <#> <fp>      Add license to existing package
  --list                                    List all license packages
  --quick <fingerprint> <tier>              Quick single license generation

Examples:
  python license_manager.py --generate-keys
  python license_manager.py --new-customer "Jonas Petraitis" 3 lifetime
  python license_manager.py --add-fingerprint license_package_jonas_petraitis_2025-01-15.txt 1 abc123-def456
  python license_manager.py --quick abc123-def456 1month
"""

import json
import base64
import datetime
import sys
from pathlib import Path
from typing import Optional, Tuple

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    from cryptography.hazmat.primitives import serialization
    from cryptography.exceptions import InvalidSignature
except ImportError:
    print("ERROR: cryptography library not installed")
    print("Install with: pip install cryptography")
    sys.exit(1)


PRODUCT_NAME = "TrackNote"
PRIVATE_KEY_FILE = "private.key"
PUBLIC_KEY_FILE = "public.key"


def _b64url_encode(b: bytes) -> str:
    """Encode bytes as base64url (no padding)."""
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """Decode base64url string to bytes."""
    s = s.replace("-", "+").replace("_", "/")
    pad = "=" * (-len(s) % 4)
    return base64.b64decode(s + pad)


def generate_keypair():
    """
    Generate Ed25519 keypair for license signing.
    Run this ONCE and store keys securely.
    """
    print("=" * 60)
    print("Generating Ed25519 Keypair")
    print("=" * 60)
    
    # Generate
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    # Serialize
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    
    private_b64 = _b64url_encode(private_bytes)
    public_b64 = _b64url_encode(public_bytes)
    
    # Display
    print()
    print("PRIVATE KEY (keep secret, never share!):")
    print("-" * 60)
    print(private_b64)
    print("-" * 60)
    print()
    print("PUBLIC KEY (put this in app.py):")
    print("-" * 60)
    print(public_b64)
    print("-" * 60)
    print()
    
    # Save to files
    Path(PRIVATE_KEY_FILE).write_text(private_b64, encoding="utf-8")
    Path(PUBLIC_KEY_FILE).write_text(public_b64, encoding="utf-8")
    
    print(f"✓ Keys saved to {PRIVATE_KEY_FILE} and {PUBLIC_KEY_FILE}")
    print()
    print("NEXT STEPS:")
    print(f"1. Copy the PUBLIC KEY into app.py:")
    print(f'   PUBLIC_KEY_B64 = "{public_b64}"')
    print()
    print(f"2. Store {PRIVATE_KEY_FILE} in a SECURE location:")
    print("   - Encrypted USB drive")
    print("   - Password manager")
    print("   - Hardware security key")
    print()
    print(f"3. NEVER commit {PRIVATE_KEY_FILE} to version control!")
    print(f"   Add to .gitignore: {PRIVATE_KEY_FILE}")
    print()
    print("=" * 60)


def load_private_key() -> Ed25519PrivateKey:
    """Load private key from file."""
    if not Path(PRIVATE_KEY_FILE).exists():
        print(f"ERROR: {PRIVATE_KEY_FILE} not found!")
        print("Generate keys first with: python license_manager.py --generate-keys")
        sys.exit(1)
    
    try:
        private_b64 = Path(PRIVATE_KEY_FILE).read_text(encoding="utf-8").strip()
        private_bytes = _b64url_decode(private_b64)
        return Ed25519PrivateKey.from_private_bytes(private_bytes)
    except Exception as e:
        print(f"ERROR: Failed to load private key: {e}")
        sys.exit(1)


def calculate_expiry(tier: str) -> Optional[str]:
    """
    Calculate expiry date based on pricing tier.
    
    Args:
        tier: "1month", "3month", or "lifetime"
    
    Returns:
        ISO date string "YYYY-MM-DD" or None for lifetime
    """
    today = datetime.date.today()
    
    if tier == "1month":
        expiry = today + datetime.timedelta(days=30)
        return expiry.isoformat()
    elif tier == "3month":
        expiry = today + datetime.timedelta(days=90)
        return expiry.isoformat()
    elif tier == "lifetime":
        return None  # No expiry
    else:
        raise ValueError(f"Invalid tier: {tier}. Use: 1month, 3month, or lifetime")


def generate_license(fingerprint: str, tier: str, customer_id: str = "") -> str:
    """
    Generate a license key.
    
    Args:
        fingerprint: Machine fingerprint from customer's computer
        tier: "1month", "3month", or "lifetime"
        customer_id: Optional customer identifier for your records
    
    Returns:
        License key string
    """
    fingerprint = fingerprint.lower().strip()
    expiry_date = calculate_expiry(tier)
    
    # Build payload
    payload = {
        "fp": fingerprint,
        "prod": PRODUCT_NAME,
        "exp": expiry_date,
        "tier": tier
    }
    
    # Add customer ID if provided (not verified, just for your tracking)
    if customer_id:
        payload["cid"] = customer_id
    
    # Serialize and sign
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    payload_b64 = _b64url_encode(payload_bytes)
    
    private_key = load_private_key()
    signature = private_key.sign(payload_bytes)
    sig_b64 = _b64url_encode(signature)
    
    return f"{payload_b64}.{sig_b64}"


def generate_customer_package(customer_name: str, num_computers: int, tier: str):
    """
    Generate a complete license package for a customer with multiple computers.
    """
    print("=" * 70)
    print(f"Generating License Package for: {customer_name}")
    print("=" * 70)
    print(f"Computers: {num_computers}")
    print(f"Tier: {tier}")
    print(f"Expiry: {calculate_expiry(tier) or 'Never (lifetime)'}")
    print()
    
    # Customer ID for tracking (sanitize name)
    customer_id = customer_name.lower().replace(" ", "_")
    
    # Create output file
    output_file = f"license_package_{customer_id}_{datetime.date.today().isoformat()}.txt"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write(f"TrackNote License Package\n")
        f.write("=" * 70 + "\n")
        f.write(f"Customer: {customer_name}\n")
        f.write(f"Date: {datetime.datetime.now().isoformat()}\n")
        f.write(f"Tier: {tier}\n")
        f.write(f"Expires: {calculate_expiry(tier) or 'Never (lifetime)'}\n")
        f.write(f"Computers: {num_computers}\n")
        f.write("\n")
        f.write("INSTRUCTIONS FOR CUSTOMER:\n")
        f.write("-" * 70 + "\n")
        f.write("1. Install TrackNote on each computer\n")
        f.write("2. On first launch, go to Help → 'Show Machine Fingerprint'\n")
        f.write("3. Send all fingerprints back to us\n")
        f.write("4. We will send you the license keys for each computer\n")
        f.write("\n")
        f.write("NOTE: You need ONE license per computer, but you can use\n")
        f.write("the SAME Google Sheet credentials on all computers.\n")
        f.write("\n")
        f.write("=" * 70 + "\n\n")
        
        # Placeholder for licenses
        for i in range(1, num_computers + 1):
            f.write(f"COMPUTER #{i}\n")
            f.write("-" * 70 + "\n")
            f.write(f"Fingerprint: [WAITING FOR CUSTOMER]\n")
            f.write(f"License Key: [WILL BE GENERATED AFTER FINGERPRINT RECEIVED]\n")
            f.write("\n\n")
    
    print(f"✓ Created: {output_file}")
    print()
    print("NEXT STEPS:")
    print("1. Send this file to customer")
    print("2. Wait for them to send fingerprints")
    print("3. Run: python license_manager.py --add-fingerprint <file> <#> <fingerprint>")
    print()


def add_license_to_package(package_file: str, computer_num: int, fingerprint: str):
    """Add a generated license to an existing package file."""
    # Read existing package
    content = Path(package_file).read_text(encoding='utf-8')
    
    # Extract tier from file
    tier = None
    for line in content.split('\n'):
        if line.startswith('Tier:'):
            tier = line.split(':')[1].strip()
            break
    
    if not tier:
        print("ERROR: Could not find tier in package file")
        return
    
    # Extract customer ID
    customer_id = Path(package_file).stem.replace('license_package_', '').rsplit('_', 1)[0]
    
    # Generate license
    license_key = generate_license(fingerprint, tier, customer_id)
    
    # Update package file
    lines = content.split('\n')
    new_lines = []
    in_computer_section = False
    current_computer = 0
    
    for line in lines:
        if line.startswith(f"COMPUTER #"):
            current_computer = int(line.split('#')[1])
            in_computer_section = (current_computer == computer_num)
        
        if in_computer_section:
            if line.startswith("Fingerprint:"):
                line = f"Fingerprint: {fingerprint}"
            elif line.startswith("License Key:"):
                line = f"License Key: {license_key}"
        
        new_lines.append(line)
    
    # Write back
    Path(package_file).write_text('\n'.join(new_lines), encoding='utf-8')
    
    print(f"✓ Added license for Computer #{computer_num}")
    print(f"  Fingerprint: {fingerprint}")
    print(f"  License: {license_key[:40]}...")
    print()


def list_active_licenses(license_dir: Path = Path(".")):
    """List all license packages and their status."""
    print("=" * 70)
    print("Active License Packages")
    print("=" * 70)
    
    packages = sorted(license_dir.glob("license_package_*.txt"))
    
    if not packages:
        print("No license packages found.")
        return
    
    for pkg in packages:
        content = pkg.read_text(encoding='utf-8')
        
        # Parse info
        customer = tier = expiry = None
        computers_done = 0
        computers_total = 0
        
        for line in content.split('\n'):
            if line.startswith('Customer:'):
                customer = line.split(':', 1)[1].strip()
            elif line.startswith('Tier:'):
                tier = line.split(':', 1)[1].strip()
            elif line.startswith('Expires:'):
                expiry = line.split(':', 1)[1].strip()
            elif line.startswith('Computers:'):
                computers_total = int(line.split(':')[1].strip())
            elif "License Key:" in line and "[WILL BE GENERATED" not in line:
                computers_done += 1
        
        # Status
        status = f"{computers_done}/{computers_total} licenses generated"
        
        print(f"\n{pkg.name}")
        print(f"  Customer: {customer}")
        print(f"  Tier: {tier}")
        print(f"  Expires: {expiry}")
        print(f"  Status: {status}")


def main():
    """Main CLI interface."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1]
    
    # Generate keypair
    if command == "--generate-keys":
        generate_keypair()
        return
    
    # List packages
    if command == "--list":
        list_active_licenses()
        return
    
    # New customer package
    if command == "--new-customer":
        if len(sys.argv) < 5:
            print("Usage: --new-customer <customer_name> <num_computers> <tier>")
            print('Example: --new-customer "Jonas Petraitis" 3 lifetime')
            sys.exit(1)
        
        customer_name = sys.argv[2]
        num_computers = int(sys.argv[3])
        tier = sys.argv[4].lower()
        
        generate_customer_package(customer_name, num_computers, tier)
        return
    
    # Add fingerprint to package
    if command == "--add-fingerprint":
        if len(sys.argv) < 5:
            print("Usage: --add-fingerprint <package_file> <computer_num> <fingerprint>")
            print('Example: --add-fingerprint license_package_jonas_2025-01-15.txt 1 abc123-def456')
            sys.exit(1)
        
        package_file = sys.argv[2]
        computer_num = int(sys.argv[3])
        fingerprint = sys.argv[4]
        
        add_license_to_package(package_file, computer_num, fingerprint)
        return
    
    # Quick single license
    if command == "--quick":
        if len(sys.argv) < 4:
            print("Usage: --quick <fingerprint> <tier>")
            print('Example: --quick abc123-def456 1month')
            sys.exit(1)
        
        fingerprint = sys.argv[2]
        tier = sys.argv[3].lower()
        
        license_key = generate_license(fingerprint, tier)
        expiry = calculate_expiry(tier)
        
        print("=" * 70)
        print("License Generated")
        print("=" * 70)
        print(f"Fingerprint: {fingerprint}")
        print(f"Tier: {tier}")
        print(f"Expires: {expiry or 'Never (lifetime)'}")
        print()
        print("License Key:")
        print("-" * 70)
        print(license_key)
        print("-" * 70)
        
        # Save to file
        output = f"license_{fingerprint[:12]}_{tier}.txt"
        Path(output).write_text(
            f"TrackNote License\n"
            f"Fingerprint: {fingerprint}\n"
            f"Tier: {tier}\n"
            f"Expires: {expiry or 'Never'}\n"
            f"\nLicense Key:\n{license_key}\n",
            encoding='utf-8'
        )
        print(f"\n✓ Saved to: {output}")
        return
    
    print(f"Unknown command: {command}")
    print(__doc__)
    sys.exit(1)


if __name__ == "__main__":
    main()