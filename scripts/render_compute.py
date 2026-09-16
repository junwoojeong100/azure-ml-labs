import argparse
from pathlib import Path

import yaml

from mlops_lab.config import ARTIFACTS, ROOT, Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve lab compute templates without embedding credentials")
    parser.add_argument("--identity-id", required=True)
    args = parser.parse_args()
    settings = Settings.load()
    for template, name in (
        ("compute-cluster.yml", settings.compute_cluster),
        ("compute-instance.yml", settings.compute_instance),
    ):
        content = (ROOT / "infra" / template).read_text()
        content = content.replace("<COMPUTE_IDENTITY_RESOURCE_ID>", args.identity_id)
        definition = yaml.safe_load(content)
        definition["name"] = name
        output = ARTIFACTS / "infra" / template
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(yaml.safe_dump(definition, sort_keys=False))
        print(output)


if __name__ == "__main__":
    main()
