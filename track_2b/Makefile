.PHONY: run

# Starts the project in a Docker container. Works from a clean checkout.
# Optional: set LLM_NAME, LLM_BASE_URL and LLM_API_KEY in the environment to
# have answers phrased by an Apertus endpoint; without them the app answers
# directly from the data.
run:
	docker build -t nearby-stars-plain-words .
	docker run --rm -p 8000:8000 \
		-e LLM_NAME -e LLM_BASE_URL -e LLM_API_KEY \
		nearby-stars-plain-words
