git clone --recursive https://gitlab.kimetrica.com/DARPA/darpa.git
cd darpa/kiluigi
git checkout master
cd ..

sed -i '4s/kiluigi\///g' env.example

# NOTE - You must change the env.example CKAN creds manually right now as Kimetrica hasn't made them public.  Do this before the next step
cp env.example kiluigi/.env
cp luigi.cfg.example luigi.cfg
cd kiluigi
sed -i '58s/1000M/10000M/' docker-compose.yml
cd ../../
cp run.py darpa/
cd darpa/kiluigi
docker-compose run --entrypoint=bash scheduler
