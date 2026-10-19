"""carbon-atlas: the collection program.

Seven commands, in `atlas.__main__`:

    python -m atlas backfill    fill the years that the sources still serve
    python -m atlas daily       collect the last days, then export the portal JSON
    python -m atlas snap        capture the forward forecast curve of each source
    python -m atlas export      write portal/data/*.json again from the store
    python -m atlas status      print what the store holds, and the failures
    python -m atlas verify      check every raw payload against its stored hash
    python -m atlas serve       give the portal at a local address

See `RUNNING.md` for the commands and the schedule, and `REFERENCE.md` for the data
model and for what a number means.
"""

__version__ = "0.1.0"
