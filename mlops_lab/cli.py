import argparse
import json
from pathlib import Path

from mlops_lab.config import ROOT, Settings
from mlops_lab.data import generate_data
from mlops_lab.operations import (
    cleanup_runtime, deploy, download_report, failed_step_logs, invoke, register_model, set_traffic,
    snapshot_run, submit, wait_for_deployment, wait_for_run,
)
from mlops_lab.pipeline import register_assets


def main() -> None:
    parser = argparse.ArgumentParser(description="Azure ML Studio/Compute MLOps lab (SDK v2)")
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument(
        "--managed-identity-client-id",
        help="Use this explicitly selected managed identity when running inside Azure",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("generate-data", help="Generate local synthetic data without Azure access")
    commands.add_parser("assets", help="Register versioned data and reusable components")
    create = commands.add_parser("submit", help="Submit a pipeline without waiting")
    create.add_argument("--run", required=True)
    create.add_argument("--data-version", choices=["1", "2"], required=True)
    create.add_argument("--alpha", type=float, default=1.0)
    create.add_argument("--max-rmse", type=float, default=3.0)
    create.add_argument("--force-rerun", action="store_true", help="Run every step instead of reusing cached outputs")
    for name in ("wait", "inspect", "report", "logs"):
        command = commands.add_parser(name)
        command.add_argument("--run", required=True)
        if name == "wait":
            command.add_argument("--timeout", type=int, default=2400)
    register = commands.add_parser("register")
    register.add_argument("--run", required=True)
    register.add_argument("--version", required=True)
    deployment = commands.add_parser("deploy")
    deployment.add_argument("--model-version", required=True)
    deployment.add_argument("--deployment", choices=["blue", "green"], required=True)
    deployment.add_argument("--no-wait", action="store_true", help="Submit only; readiness must be checked separately")
    deployment_wait = commands.add_parser("wait-deployment")
    deployment_wait.add_argument("--deployment", choices=["blue", "green"], required=True)
    deployment_wait.add_argument("--timeout", type=int, default=2400)
    traffic = commands.add_parser("traffic")
    traffic.add_argument("--deployment", choices=["blue", "green"], required=True)
    prediction = commands.add_parser("invoke")
    prediction.add_argument("--deployment", choices=["blue", "green"])
    cleanup = commands.add_parser("cleanup-runtime")
    cleanup.add_argument(
        "--delete-endpoint", action="store_true",
        help="Delete only this lab's tagged endpoint and all of its deployments",
    )
    args = parser.parse_args()
    if args.command == "generate-data":
        result = generate_data()
    else:
        settings = Settings.load(args.config)
        client = settings.client(args.managed_identity_client_id)
        if args.command == "assets":
            result = register_assets(client, settings)
        elif args.command == "submit":
            result = submit(
                client, settings, args.run, args.data_version, args.alpha, args.max_rmse,
                force_rerun=args.force_rerun,
            )
        elif args.command == "wait":
            result = wait_for_run(client, settings, args.run, args.timeout)
        elif args.command == "inspect":
            result = snapshot_run(client, settings, args.run)
        elif args.command == "report":
            result = download_report(client, settings, args.run)
        elif args.command == "logs":
            result = failed_step_logs(client, settings, args.run)
        elif args.command == "register":
            result = register_model(client, settings, args.run, args.version)
        elif args.command == "deploy":
            result = deploy(client, settings, args.model_version, args.deployment, wait=not args.no_wait)
        elif args.command == "wait-deployment":
            result = wait_for_deployment(client, settings, args.deployment, args.timeout)
        elif args.command == "traffic":
            result = set_traffic(client, settings, args.deployment)
        elif args.command == "invoke":
            result = invoke(client, settings, args.deployment)
        elif args.command == "cleanup-runtime":
            result = cleanup_runtime(client, settings, args.delete_endpoint)
        else:
            parser.error("Unknown operation.")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
