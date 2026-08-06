import argparse

import f1_fantasy.cli
import league.cli


def main():
    parser = argparse.ArgumentParser(description="F1 Fantasy points lookup and draft league tracker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    f1_fantasy.cli.add_subcommands(subparsers)
    league.cli.add_subcommands(subparsers)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
