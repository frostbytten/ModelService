import docker
import re
import configparser
import redis

class KiController(object):
    """
    A controller to manage Kimetrica model execution.
    """

    def __init__(self, model_config):
        self.bucket = "world-modelers"
        
        # Rework this all later by pulling from yml or other config.  For now this works...
        self.model_map = {
		"malnutrition_model":{
			"key":"results/malnutrition_model/" + model_config["config"]["run_id"] + ".geojson",
			"entrypoint":f"python run.py --bucket={self.bucket} --model_name=malnutrition_model --task_name=MalnutritionGeoJSON --result_name=final/malnutrition.geojson --key=" + "results/malnutrition_model/" + model_config["config"]["run_id"] + ".geojson " + "--params PercentOfNormalRainfall|" + str(model_config["config"].get("percent_of_normal_rainfall",""))
				    },
                "population_model":{
			"key":"results/population_model/" + model_config["config"]["run_id"] + ".csv",
                        "entrypoint":f"python run.py --bucket={self.bucket} --model_name=population_model --task_name=EstimatePopulation --result_name=final/population_estimate.csv  --key=" + "results/population_model/" + model_config["config"]["run_id"] + ".csv"
				   }
        }
        config = configparser.ConfigParser()
        config.read('config.ini')
        
        self.install_path = config["MALNUTRITION"]["INSTALL_PATH"]
        self.s3_cred_path = config["MALNUTRITION"]["S3_CRED_PATH"]
        
        self.model_config = model_config
        self.client = docker.from_env()
        self.containers = self.client.containers
        self.scheduler = 'drp_scheduler:latest'
        self.db = 'drp_db:latest'
        self.db_name = 'kiluigi-db'
        
        # These are now pulled from model_map above
        self.key = self.model_map[model_config["name"]]["key"]
        self.entrypoint=self.model_map[model_config["name"]]["entrypoint"]

        self.volumes = {self.s3_cred_path:{'bind':'/root/.aws','mode':'rw'},self.install_path: {'bind': '/usr/src/app', 'mode': 'rw'}}
        self.environment = self.parse_env_file(self.install_path + '/kiluigi/.env')
        self.db_ports = {'5432/tcp': 5432}
        self.network_name = "kiluigi"
        self.environment['PYTHONPATH'] = '/usr/src/app:/usr/src/app/kiluigi'
        self.db_environment = {"APP": self.environment["APP"],
                          "ENV": self.environment["ENV"],
                          "PGPASSWORD": self.environment["PGPASSWORD"],
                          "POSTGRES_PASSWORD": self.environment["PGPASSWORD"]}
        self.network = self.create_network()
        self.db_container = self.run_db()


    def parse_env_file(self, path_to_file):
        """
        Parse a Kimetrica .env file into a dictionary
        Ultimately this should be deprecated in favor of
        a better approach to storing and loading environment variables
        and configurations for Kimetrica models executions.
        """
        envre = re.compile(r'''^([^\s=]+)=(?:[\s"']*)(.+?)(?:[\s"']*)$''')
        env_var = re.compile(r'\$\{[0-9a-zA-Z_]*\}')
        alpha_num = re.compile(r'[0-9a-zA-Z_]+')
        result = {}
        with open(path_to_file) as ins:
            for line in ins:
                match = envre.match(line)
                if match is not None:
                    key = match.group(1)
                    val = match.group(2)
                    to_replace = env_var.findall(val)
                    for v in to_replace:
                        found = result[alpha_num.search(v).group(0)]
                        val = val.replace(v, found)
                    result[key] = val
        return result


    def create_network(self):
        """
        Establish network for communication between
        Kimetrica Docker containers.
        """
        curr_network = self.client.networks.list(names=[self.network_name])
        if len(curr_network) > 0:
            return curr_network[0]
        else:
            network = self.client.networks.create(self.network_name, driver="bridge")
        return network


    def run_db(self):
        """
        Run KiLuigi Database Docker container.
        """
        try:
            db_container = self.containers.get(self.db_name)
        except:
            # db_container does not exist, so we must make it
            db_container = self.containers.run(self.db,
                                          environment=self.db_environment, 
                                         ports=self.db_ports, 
                                          network=self.network_name, 
                                          name=self.db_name,
                                          detach=True)    
        return db_container 


    def run_model(self):
        """
        Run KiLuigi model inside Docker container
        """
        self.model = self.containers.run(self.scheduler, 
                               environment=self.environment, 
                               volumes=self.volumes, 
                               network=self.network_name, 
                               links={self.db_container.short_id: None},
                               entrypoint=self.entrypoint,
                               detach=True)
        return self.model


    def model_logs(self):
        """
        Return model logs
        """
        model_logs = self.model.logs()
        model_logs_decoded = model_logs.decode('utf-8')
        return model_logs_decoded
