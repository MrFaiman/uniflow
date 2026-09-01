the router takes the chunks from the reciver
and corrupts the data by the following:
1. messes with the bits
2. lose some chunks on accident
3. send the data to wrong reciver

to run use:
docker compose up --build

to observe the logs use:
docker compose logs -f router