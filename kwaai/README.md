# first build:

build -t paiassistant .

# removing previous images

docker build --no-cache -t paiassistant .

# ResolutionTooDeep error:

docker build --no-cache --build-arg MAX_ROUNDS=1000000 -t paiassistant .
