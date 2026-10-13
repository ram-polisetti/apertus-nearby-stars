.PHONY: run

# The project lives in track_2b/ (Hack Apertus template layout).
# This delegates so `make run` also works from the repository root.
run:
	$(MAKE) -C track_2b run
