import modal
from modal import Image

# Setup

app = modal.App("hello")
image = Image.debian_slim().pip_install(
    "requests"
)  # this is telling modal what kind of infrastructure we want if we decide to run this python code on modal => debian_slim() means linux architecture
# so that line is saying, simple computer running linux with requests installed

# recall image is like the docker image in the Hitesh's course
# MODAL SHINES BECAUSE - 1. we can use code to describe what hardware we want to use, and 2. we can use decorators to specify which hardware should run our code

# Hello!


# a decorator to tell modal to use the image we defined above to run the code.
@app.function(image=image)
def hello() -> str:
    import requests

    response = requests.get("https://ipinfo.io/json")
    # gets our ip address from where the code is ran
    data = response.json()
    city, region, country = data["city"], data["region"], data["country"]
    return f"Hello from {city}, {region}, {country}!!"


# New - added thanks to student Tue H.!


@app.function(image=image, region="eu")
def hello_europe() -> str:
    import requests

    response = requests.get("https://ipinfo.io/json")
    data = response.json()
    city, region, country = data["city"], data["region"], data["country"]
    return f"Hello from {city}, {region}, {country}!!"
