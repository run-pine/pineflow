import datetime
import json
import logging
import os
import uuid
import warnings
from typing import Any, Dict, List, Literal, Optional, Union

import certifi
from deprecated import deprecated
from pydantic.v1 import BaseModel

os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
logging.getLogger("ibm_watsonx_ai.client").setLevel(logging.ERROR)
logging.getLogger("ibm_watsonx_ai.wml_resource").setLevel(logging.ERROR)

REGIONS_URL = {
    "us-south": {"wml": "https://us-south.ml.cloud.ibm.com", 
                 "wos": "https://api.aiopenscale.cloud.ibm.com", 
                 "factsheet": None},
    "eu-de": {"wml": "https://eu-de.ml.cloud.ibm.com", 
              "wos": "https://eu-de.api.aiopenscale.cloud.ibm.com", 
              "factsheet": "frankfurt"},
    "au-syd": {"wml": "https://au-syd.ml.cloud.ibm.com", 
               "wos": "https://au-syd.api.aiopenscale.cloud.ibm.com", 
               "factsheet": "sydney"},
}

def _filter_dict(original_dict: dict, optional_keys: List, required_keys: List = []):
    """Filters a dictionary to keep only the specified keys and check required.
    
    Args:
        original_dict (dict): The original dictionary
        optional_keys (list): A list of keys to keep
        required_keys (list, optional): A list of keys that must exist in the dictionary
    """
    # Ensure all required keys are in the source dictionary
    missing_keys = [key for key in required_keys if key not in original_dict]
    if missing_keys:
        raise KeyError(f"Missing required parameter: {missing_keys}")
    
    all_keys_to_keep = set(required_keys + optional_keys)
    
    # Create a new dictionary with only the key-value pairs where the key is in 'keys' and value is not None
    return {key: original_dict[key] for key in all_keys_to_keep if key in original_dict and original_dict[key] is not None}     

def _convert_payload_format(records: List[dict], feature_fields: List[str]) -> List[dict]:
        
        payload_data = []
        response_fields = ["generated_text", "input_token_count", "generated_token_count"]
            
        for record in records: 
            request = { "parameters": { "template_variables": {}}}
            results = {}
                
            request["parameters"]["template_variables"] = {field: str(record.get(field, "")) for field in feature_fields}
            
            results = {field: record.get(field) for field in response_fields if record.get(field)}
                
            pl_record = {"request": request, 
                         "response": {"results": [results]}, 
                         "scoring_id": str(uuid.uuid4())}
            payload_data.append(pl_record)
           
        return payload_data


class CloudPakforDataCredentials:
    """Encapsulate passed credentials for CloudPakforData.

    Args:
        url (str): Host URL of Cloud Pak for Data environment.
        api_key (str, optional): Environment api_key if IAM enabled.
        username (str, optional): Environment username.
        password (str, optional): Environment password.
        bedrock_url (str, optional): Bedrock URL. This url is required only when iam-integration is enabled on CP4D 4.0.x cluster.
        instance_id (str, optional): Instance ID.
        version (str, optional): CPD Version.
        disable_ssl_verification (bool, optional): Indicates whether verification of the server's SSL certificate. Defaults to ``True``.
    """
    
    def __init__(
        self,
        url: str,
        api_key: str = None,
        username: str = None,
        password: str = None,
        bedrock_url: str = None,
        instance_id: Literal["icp","openshift"] = None,
        version: str = None,
        disable_ssl_verification: bool = True
        ) -> None:
        
        self.url = url
        self.api_key = api_key
        self.username = username
        self.api_key = api_key
        self.password = password
        self.bedrock_url = bedrock_url
        self.instance_id = instance_id
        self.api_key = api_key
        self.version = version
        self.disable_ssl_verification = disable_ssl_verification
        
    def to_dict(self) -> dict[str, Any]:
        data = dict([(k, v) for k, v in self.__dict__.items()])
        
        if "instance_id" in data and self.instance_id.lower() not in ["icp","openshift"]:
            data.pop("instance_id")
        
        return data

class IntegratedSystemCredentials(BaseModel):
    """Encapsulate passed credentials for Integrated System.
    
    Depending on the `auth_type`, only a subset of the properties are required.

    Args:
        auth_type (str): Type of authentication. Currently supports "basic" and "bearer".
        username (str, optional): Username for Basic Auth.
        password (str, optional): Password for Basic Auth.
        token_url (str, optional): URL of the authentication endpoint used to request a Bearer token.
        token_method (str, optional): HTTP method used to request the Bearer token (e.g., "POST", "GET").
        token_headers (str, optional): Optional headers to include when requesting the token.
        token_payload (bool, optional): Body/payload to send when requesting the token. Can be a string (e.g., raw JSON).
    """
    
    auth_type: Literal["basic", "bearer"]
    username: Optional[str] # basic
    password: Optional[str] # basic
    token_url: Optional[str] # bearer
    token_method: Optional[str] # bearer
    token_headers: Optional[Dict] # bearer
    token_payload: Optional[Union[str, Dict]] # bearer
    
    def __init__(
        self, auth_type: Literal["basic", "bearer"],
        username: str = None,
        password: str = None,
        url: str = None,
        headers: Dict = {},
        payload: Union[str, Dict] = "",
        method: str = None
        ) -> None:
        
        if auth_type == "basic":
            if not username or not password:
                raise ValueError("`username` and `password` are required for auth_type = 'basic'.")
        elif auth_type == "bearer":
            if not url or not method:
                raise ValueError("`url` and `method` are required for auth_type = 'bearer'.")
        
        super().__init__(
            auth_type=auth_type,
            username=username,
            password=password,
            url=url,
            headers=headers,
            payload=payload,
            method=method)
      
    def to_dict(self) -> Dict:
        
        integrated_system_creds = { "auth_type": self.auth_type }
        
        if self.auth_type == "basic":
            integrated_system_creds["username"] = self.username
            integrated_system_creds["password"] = self.password
        elif self.auth_type == "bearer":
            integrated_system_creds["token_info"] = { 
                                                     "url": self.token_url,
                                                     "headers": self.token_headers,
                                                     "payload": self.token_payload,
                                                     "method": self.token_method,
                                                     }
            
        return integrated_system_creds

class WatsonxExternalPromptMonitor:
    """Provides functionality to interact with IBM watsonx.governance for monitoring external LLM's.
    
    Note:
            One of these parameters is required to create prompt monitor: ``project_id`` or ``space_id``. Not both.

    Args:
        api_key (str): IBM watsonx.governance API key.
        space_id (str, optional): watsonx.governance space_id.
        project_id (str, optional): watsonx.governance project_id.
        region (str, optional): Region where the watsonx.governance is hosted when using IBM Cloud. Defaults to ``us-south``
        cpd_creds (CloudPakforDataCredentials, optional): Cloud Pak for Data environment details.

    **Example**

    .. code-block:: python

        from pineflow.monitors import WatsonxExternalPromptMonitor, CloudPakforDataCredentials

        # watsonx.governance (IBM Cloud)
        detached_watsonx_monitor = WatsonxExternalPromptMonitor(api_key="your_api_key", 
                                                                space_id="your_space_id")
                                                               
        # watsonx.governance (cp4d)
        cpd_creds = CloudPakforDataCredentials(url="your_cpd_url", 
                                               username="your_username", 
                                               password="your_password",
                                               version="5.0", 
                                               instance_id="openshift")
        
        detached_watsonx_monitor = WatsonxExternalPromptMonitor(space_id="your_space_id"
                                                                cpd_creds=cpd_creds)
    """
    
    def __init__(self,
                 api_key: str = None,
                 space_id: str = None,
                 project_id: str = None,
                 region: Literal["us-south", "eu-de", "au-syd"] = "us-south",
                 cpd_creds: CloudPakforDataCredentials | dict = None,
                 ) -> None:
        
        try:
            import ibm_aigov_facts_client  # noqa: F401
            import ibm_cloud_sdk_core.authenticators  # noqa: F401
            import ibm_watson_openscale  # noqa: F401
            import ibm_watsonx_ai  # noqa: F401

        except ImportError:
            raise ImportError("""ibm-aigov-facts-client, ibm-watson-openscale or ibm-watsonx-ai module not found, 
                                please install it with `pip install ibm-aigov-facts-client ibm-watson-openscale ibm-watsonx-ai`""")
            
        if (not (project_id or space_id)) or (project_id and space_id):
            raise ValueError("`project_id` and `space_id` parameter cannot be set at the same time.")

        self.space_id = space_id
        self.project_id = project_id
        self.region = region
        self._api_key = api_key
        self._wos_client = None
        
        self._container_id = space_id if space_id else project_id
        self._container_type = "space" if space_id else "project"
        self._deployment_stage = "production" if space_id else "development"
        
        if cpd_creds: 
            self._wos_cpd_creds = _filter_dict(cpd_creds.to_dict(), ["username", "password", "api_key", 
                                                                   "disable_ssl_verification"], ["url"])
            self._fact_cpd_creds = _filter_dict(cpd_creds.to_dict(), ["username", "password", "api_key", 
                                                                        "bedrock_url"],["url"])
            self._fact_cpd_creds["service_url"] = self._fact_cpd_creds.pop("url")
            self._wml_cpd_creds = _filter_dict(cpd_creds.to_dict(), ["username", "password", "api_key", "instance_id", 
                                                                   "version", "bedrock_url"], ["url"])
                    
    def _create_detached_prompt(self, detached_details: dict, 
                                prompt_template_details: dict, 
                                detached_asset_details: dict) -> str:
        from ibm_aigov_facts_client import (  # type: ignore
            AIGovFactsClient,
            CloudPakforDataConfig,
            DetachedPromptTemplate,
            PromptTemplate,
        )
            
        try:
            if hasattr(self, "_fact_cpd_creds") and self._fact_cpd_creds:
                cpd_creds = CloudPakforDataConfig(**self._fact_cpd_creds)
                
                aigov_client = AIGovFactsClient(
                    container_id=self._container_id,
                    container_type=self._container_type,
                    cloud_pak_for_data_configs=cpd_creds,
                    disable_tracing=True)
                
            else:
                aigov_client = AIGovFactsClient(
                    api_key=self._api_key,
                    container_id=self._container_id,
                    container_type=self._container_type,
                    disable_tracing=True,
                    region=REGIONS_URL[self.region]["factsheet"])
                
        except Exception as e:
            logging.error(f"Error connecting to IBM watsonx.governance (factsheets): {e}")
            raise

        created_detached_pta = aigov_client.assets.create_detached_prompt(
            **detached_asset_details,
            prompt_details=PromptTemplate(**prompt_template_details),
            detached_information=DetachedPromptTemplate(**detached_details))
            
        return created_detached_pta.to_dict()["asset_id"]
                  
    def _create_deployment_pta(self, asset_id: str,
                               name: str,
                               model_id: str) -> str:
        from ibm_watsonx_ai import APIClient, Credentials  # type: ignore
            
        try:
            if hasattr(self, "_wml_cpd_creds") and self._wml_cpd_creds:
                creds = Credentials(**self._wml_cpd_creds)
                
                wml_client = APIClient(creds)
                wml_client.set.default_space(self.space_id)
                
            else:
                creds = Credentials(url= REGIONS_URL[self.region]["wml"], api_key=self._api_key)
                wml_client = APIClient(creds)
                wml_client.set.default_space(self.space_id)
                
        except Exception as e:
            logging.error(f"Error connecting to IBM watsonx.ai Runtime: {e}")
            raise
            
        meta_props = {
            wml_client.deployments.ConfigurationMetaNames.PROMPT_TEMPLATE: { "id" : asset_id },
            wml_client.deployments.ConfigurationMetaNames.DETACHED: {},
            wml_client.deployments.ConfigurationMetaNames.NAME: name + " " + "deployment",
            wml_client.deployments.ConfigurationMetaNames.BASE_MODEL_ID: model_id
        }
            
        created_deployment = wml_client.deployments.create(asset_id, meta_props)
            
        return wml_client.deployments.get_uid(created_deployment)
    
    @deprecated(
        version="0.6.8",
        reason="'create_prompt_monitor' is deprecated and will be removed in next release, use 'add_prompt_monitor'.",
    )
    def create_prompt_monitor(self,
                              name: str,
                              model_id: str,
                              task_id: Literal["retrieval_augmented_generation", "summarization"],
                              detached_model_provider: str,
                              description: str = "",
                              model_parameters: dict = None,
                              detached_model_name: str = None,
                              detached_model_url: str = None,
                              detached_prompt_url: str = None,
                              detached_prompt_additional_info: dict = None,
                              prompt_variables: List[str] = None,
                              input_text: str = None,
                              context_fields: List[str] = None,
                              question_field: str = None) -> dict:
        """DEPRECATED: use 'add_prompt_monitor'."""
        return self.add_prompt_monitor(name,
                                       model_id,
                                       task_id,
                                       detached_model_provider,
                                       description,
                                       model_parameters,
                                       detached_model_name,
                                       detached_model_url,
                                       detached_prompt_url,
                                       detached_prompt_additional_info,
                                       prompt_variables,
                                       input_text,
                                       context_fields,
                                       question_field
                                       )
             
    def add_prompt_monitor(self,
                              name: str,
                              model_id: str,
                              task_id: Literal["retrieval_augmented_generation", "summarization"],
                              detached_model_provider: str,
                              description: str = "",
                              model_parameters: dict = None,
                              detached_model_name: str = None,
                              detached_model_url: str = None,
                              detached_prompt_url: str = None,
                              detached_prompt_additional_info: dict = None,
                              prompt_variables: List[str] = None,
                              input_text: str = None,
                              context_fields: List[str] = None,
                              question_field: str = None) -> dict:
        """Create a Detached/External Prompt Template Asset and setup monitors for a given prompt template asset.

        Args:
            name (str): The name of the External Prompt Template Asset..
            model_id (str): Id of the model associated with the prompt.
            task_id (str): The task identifier. Currently supports "retrieval_augmented_generation" and "summarization" tasks.
            detached_model_provider (str): The external model provider.
            description (str, optional): Description of the External Prompt Template Asset.
            model_parameters (dict, optional): Model parameters and their respective values.
            detached_model_name (str, optional): The name of the external model.
            detached_model_url (str, optional): URL of the external model.
            detached_prompt_url (str, optional): URL of the external prompt.
            detached_prompt_additional_info (dict, optional): Additional information related to the external prompt.
            prompt_variables (List[str], optional): Values for prompt variables.
            input_text (str, optional): The input text for the prompt.
            context_fields (List[str], optional): A list of fields that will provide context to the prompt. Applicable only for ``retrieval_augmented_generation`` problem type.
            question_field (str, optional): The field containing the question to be answered. Applicable only for ``retrieval_augmented_generation`` problem type.

        **Example**

        .. code-block:: python

            detached_watsonx_monitor.create_prompt_monitor(name="Detached prompt (model AWS Anthropic)",
                                                    model_id="anthropic.claude-v2",
                                                    task_id="retrieval_augmented_generation",
                                                    detached_model_provider="AWS Bedrock",
                                                    detached_model_name="Anthropic Claude 2.0",
                                                    detached_model_url="https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-claude.html",
                                                    prompt_variables=["context1", "context2", "input_query"],
                                                    input_text="Prompt text to be given",
                                                    context_fields=["context1", "context2"],
                                                    question_field="input_query")
            
        """
        prompt_metadata = locals()
        # remove unused vars from dict
        prompt_metadata.pop("self", None)
        prompt_metadata.pop("context_fields", None)
        prompt_metadata.pop("question_field", None)
        
        # update name of keys to aigov_facts api
        prompt_metadata["input"] = prompt_metadata.pop("input_text", None)
        prompt_metadata["model_provider"] = prompt_metadata.pop("detached_model_provider", None)
        prompt_metadata["model_name"] = prompt_metadata.pop("detached_model_name", None)
        prompt_metadata["model_url"] = prompt_metadata.pop("detached_model_url", None)
        prompt_metadata["prompt_url"] = prompt_metadata.pop("detached_prompt_url", None)
        prompt_metadata["prompt_additional_info"] = prompt_metadata.pop("detached_prompt_additional_info", None)
        
        # update list of vars to dict
        prompt_metadata["prompt_variables"] = { prompt_var: "" for prompt_var in prompt_metadata["prompt_variables"] }
        
        from ibm_watson_openscale import APIClient as WosAPIClient  # type: ignore
        
        if not self._wos_client:   
            try:
                if hasattr(self, "_wos_cpd_creds") and self._wos_cpd_creds:
                    from ibm_cloud_sdk_core.authenticators import (
                        CloudPakForDataAuthenticator,  # type: ignore
                    )
                    
                    authenticator = CloudPakForDataAuthenticator(**self._wos_cpd_creds)
                    self._wos_client = WosAPIClient(authenticator=authenticator, 
                                                    service_url=self._wos_cpd_creds["url"])
                    
                else:
                    from ibm_cloud_sdk_core.authenticators import (
                        IAMAuthenticator,  # type: ignore
                    )
                    
                    authenticator = IAMAuthenticator(apikey=self._api_key)
                    self._wos_client = WosAPIClient(authenticator=authenticator, service_url=REGIONS_URL[self.region]["wos"])
                    
            except Exception as e:
                logging.error(f"Error connecting to IBM watsonx.governance (openscale): {e}")
                raise
            
        detached_details = _filter_dict(prompt_metadata, 
                                        ["model_name", "model_url", "prompt_url", "prompt_additional_info"],
                                        ["model_id", "model_provider"])
        detached_details["prompt_id"] = "detached_prompt_" + str(uuid.uuid4())
        
        prompt_details = _filter_dict(prompt_metadata, 
                                      ["prompt_variables", "input", "model_parameters"])
        
        detached_asset_details = _filter_dict(prompt_metadata, ["description"],
                                              ["name", "model_id", "task_id"])
        
        detached_pta_id = self._create_detached_prompt(detached_details, prompt_details, detached_asset_details)
        deployment_id = None
        if self._container_type == "space":
            deployment_id =  self._create_deployment_pta(detached_pta_id, name, model_id)
            
        monitors = {
            "generative_ai_quality": {
                "parameters": {
                    "min_sample_size": 10,
                    "metrics_configuration":{}
                    }
                }}
        
        max_attempt_execute_prompt_setup = 0
        while max_attempt_execute_prompt_setup < 2:
            try:
                generative_ai_monitor_details = self._wos_client.wos.execute_prompt_setup(
                    prompt_template_asset_id = detached_pta_id, 
                    space_id = self.space_id,
                    project_id=self.project_id,
                    deployment_id = deployment_id,
                    label_column = "reference_output",
                    context_fields=context_fields,     
                    question_field = question_field,   
                    operational_space_id = self._deployment_stage, 
                    problem_type = task_id,
                    input_data_type = "unstructured_text", 
                    supporting_monitors = monitors, 
                    background_mode = False).result
                
                break
                
            except Exception as e:
                if e.code == 403 and "The user entitlement does not exist" in e.message \
                and max_attempt_execute_prompt_setup < 1:
                    max_attempt_execute_prompt_setup = max_attempt_execute_prompt_setup + 1
                    
                    data_marts = self._wos_client.data_marts.list().result
                    if (data_marts.data_marts is None) or (not data_marts.data_marts):
                        raise ValueError("Error retrieving IBM watsonx.governance (openscale) data mart. \
                                         Make sure the data mart are configured.")
                        
                    data_mart_id = data_marts.data_marts[0].metadata.id
                    
                    self._wos_client.wos.add_instance_mapping(
                        service_instance_id=data_mart_id,
                        space_id=self.space_id,
                        project_id=self.project_id)
                else:
                    max_attempt_execute_prompt_setup = 2
                    raise e

        generative_ai_monitor_details = generative_ai_monitor_details._to_dict()   
               
        return {"detached_prompt_template_asset_id": detached_pta_id,
                "deployment_id": deployment_id,
                "subscription_id": generative_ai_monitor_details["subscription_id"]} 
    
    @deprecated(
        version="0.6.8",
    )
    def payload_logging(self, payload_records: List[dict], subscription_id: str) -> None:
        """DEPRECATED: use 'store_payload_records'."""
        return self.store_payload_records(payload_records, subscription_id)  

    @deprecated(
        version="0.6.11",
        reason="'add_payload_records' is deprecated and will be removed in next release, use 'store_payload_records'.",
    )
    def add_payload_records(self, payload_records: List[dict], subscription_id: str) -> None:
        """DEPRECATED: use 'store_payload_records'."""
        return self.store_payload_records(payload_records, subscription_id)
                     
    def store_payload_records(
        self, 
        records_request: List[dict], 
        subscription_id: str, 
        payload_records: List[dict] = None
        ) -> List[str]:
        """Store records to payload logging.

        Args:
            records_request (List[dict]): 
            subscription_id (str): 

        **Example**

        .. code-block:: python

            detached_watsonx_monitor.store_payload_records(records_request=[{"context1": "value_context1",
                                                    "context2": "value_context1",
                                                    "input_query": "What's Pineflow?",
                                                    "input_token_count": 25,
                                                    "generated_token_count": 150}], 
                                            subscription_id="5d62977c-a53d-4b6d-bda1-7b79b3b9d1a0")
        """
        # START deprecated params message
        if payload_records is not None:
            warnings.warn(
                "'payload_records' is deprecated and will be removed in a future version. "
                "Please use 'records_request' instead.",
                DeprecationWarning,
                stacklevel=2
            )
            if records_request is None:
                records_request = payload_records
        # END deprecated params message        
        from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
        from ibm_watson_openscale import APIClient as WosAPIClient
        from ibm_watson_openscale.supporting_classes.enums import (
            DataSetTypes,
            TargetTypes,
        )
        
        if not self._wos_client:
            try:
                if hasattr(self, "_wos_cpd_creds") and self._wos_cpd_creds:
                    from ibm_cloud_sdk_core.authenticators import (
                        CloudPakForDataAuthenticator,  # type: ignore
                    )
                    
                    authenticator = CloudPakForDataAuthenticator(**self._wos_cpd_creds)
                    self._wos_client = WosAPIClient(authenticator=authenticator, 
                                                    service_url=self._wos_cpd_creds["url"])
                    
                else:
                    from ibm_cloud_sdk_core.authenticators import (
                        IAMAuthenticator,  # type: ignore
                    )
                    
                    authenticator = IAMAuthenticator(apikey=self._api_key)
                    self._wos_client = WosAPIClient(authenticator=authenticator, service_url=REGIONS_URL[self.region]["wos"])
                
            except Exception as e:
                logging.error(f"Error connecting to IBM watsonx.governance (openscale): {e}")
                raise
        
        subscription_details = self._wos_client.subscriptions.get(subscription_id).result
        subscription_details = json.loads(str(subscription_details))
            
        feature_fields = subscription_details["entity"]["asset_properties"]["feature_fields"]
            
        payload_data_set_id = self._wos_client.data_sets.list(type=DataSetTypes.PAYLOAD_LOGGING,
                                                              target_target_id=subscription_id, 
                                                              target_target_type=TargetTypes.SUBSCRIPTION).result.data_sets[0].metadata.id
            
        payload_data = _convert_payload_format(records_request, feature_fields)
        self._wos_client.data_sets.store_records(data_set_id=payload_data_set_id, 
                                                 request_body=payload_data,
                                                 background_mode=True)
        
        return [data["scoring_id"]+"-1" for data in payload_data]               

# DEPRECATED remove in next release
class WatsonxExternalPromptMonitoring(WatsonxExternalPromptMonitor):
    def __init__(self, *args, **kwargs):
        warnings.warn(
            "'WatsonxExternalPromptMonitoring' is deprecated and will be removed. Use 'WatsonxExternalPromptMonitor' instead.",
            DeprecationWarning,
            stacklevel=2
        )
        super().__init__(*args, **kwargs)
     
class WatsonxPromptMonitor:
    """Provides functionality to interact with IBM watsonx.governance for monitoring IBM watsonx.ai LLM's.
    
    Note:
        One of these parameters is required to create prompt monitor: ``project_id`` or ``space_id``. Not both.

    Args:
        api_key (str): IBM watsonx.governance API key.
        space_id (str, optional): watsonx.governance space_id.
        project_id (str, optional): watsonx.governance project_id.
        region (str, optional): Region where the watsonx.governance is hosted when using IBM Cloud. Defaults to ``us-south``
        cpd_creds (CloudPakforDataCredentials, optional): Cloud Pak for Data environment details.

    **Example**

    .. code-block:: python

        from pineflow.monitors import WatsonxPromptMonitor, CloudPakforDataCredentials

        # watsonx.governance (IBM Cloud)
        watsonx_monitor = WatsonxPromptMonitor(api_key="your_api_key", 
                                               space_id="your_space_id")
        
        # watsonx.governance (cp4d)
        cpd_creds = CloudPakforDataCredentials(url="your_cpd_url", 
                                               username="your_username", 
                                               password="your_password",
                                               version="5.0", 
                                               instance_id="openshift")
        
        watsonx_monitor = WatsonxPromptMonitor(space_id="your_space_id"
                                               cpd_creds=cpd_creds)                                            
    """
    
    def __init__(self,
                 api_key: str =None,
                 space_id: str = None,
                 project_id: str = None,
                 region: Literal["us-south", "eu-de", "au-syd"] = "us-south",
                 cpd_creds: CloudPakforDataCredentials | dict = None,
                 ) -> None:
        try:
            import ibm_aigov_facts_client  # noqa: F401
            import ibm_cloud_sdk_core.authenticators  # noqa: F401
            import ibm_watson_openscale  # noqa: F401
            import ibm_watsonx_ai  # noqa: F401

        except ImportError:
            raise ImportError("""ibm-aigov-facts-client, ibm-watson-openscale or ibm-watsonx-ai module not found, 
                                please install it with `pip install ibm-aigov-facts-client ibm-watson-openscale ibm-watsonx-ai`""")
            
        if (not (project_id or space_id)) or (project_id and space_id):
            raise ValueError("`project_id` and `space_id` parameter cannot be set at the same time.")

        self.space_id = space_id
        self.project_id = project_id
        self.region = region
        self._api_key = api_key
        self._wos_client = None
        
        self._container_id = space_id if space_id else project_id
        self._container_type = "space" if space_id else "project"
        self._deployment_stage = "production" if space_id else "development"
        
        if cpd_creds: 
            self._wos_cpd_creds = _filter_dict(cpd_creds.to_dict(), ["username", "password", "api_key", 
                                                                   "disable_ssl_verification"], ["url"])
            self._fact_cpd_creds = _filter_dict(cpd_creds.to_dict(), ["username", "password", "api_key", 
                                                                        "bedrock_url"],["url"])
            self._fact_cpd_creds["service_url"] = self._fact_cpd_creds.pop("url")
            self._wml_cpd_creds = _filter_dict(cpd_creds.to_dict(), ["username", "password", "api_key", "instance_id", 
                                                                   "version", "bedrock_url"], ["url"])
               
    def _create_prompt_template(self, prompt_template_details: dict, asset_details: dict) -> str:
        from ibm_aigov_facts_client import (
            AIGovFactsClient,
            CloudPakforDataConfig,
            PromptTemplate,
        )
            
        try:
            if hasattr(self, "_fact_cpd_creds") and self._fact_cpd_creds:
                cpd_creds = CloudPakforDataConfig(**self._fact_cpd_creds)
                
                aigov_client = AIGovFactsClient(
                    container_id=self._container_id,
                    container_type=self._container_type,
                    cloud_pak_for_data_configs=cpd_creds,
                    disable_tracing=True)
                
            else:
                aigov_client = AIGovFactsClient(
                    api_key=self._api_key,
                    container_id=self._container_id,
                    container_type=self._container_type,
                    disable_tracing=True,
                    region=REGIONS_URL[self.region]["factsheet"])
                
        except Exception as e:
            logging.error(f"Error connecting to IBM watsonx.governance (factsheets): {e}")
            raise

        created_pta = aigov_client.assets.create_prompt(
            **asset_details, 
            input_mode="freeform",
            prompt_details=PromptTemplate(**prompt_template_details))
            
        return created_pta.to_dict()["asset_id"]
                 
    def _create_deployment_pta(self, asset_id: str,
                               name: str,
                               model_id: str) -> str:
        from ibm_watsonx_ai import APIClient, Credentials  # type: ignore
            
        try:
            if hasattr(self, "_wml_cpd_creds") and self._wml_cpd_creds:
                creds = Credentials(**self._wml_cpd_creds)
                
                wml_client = APIClient(creds)
                wml_client.set.default_space(self.space_id)

            else:
                creds = Credentials(url= REGIONS_URL[self.region]["wml"], api_key=self._api_key)
                
                wml_client = APIClient(creds)
                wml_client.set.default_space(self.space_id)
                
        except Exception as e:
            logging.error(f"Error connecting to IBM watsonx.ai Runtime: {e}")
            raise
            
        meta_props = {
            wml_client.deployments.ConfigurationMetaNames.PROMPT_TEMPLATE: { "id" : asset_id },
            wml_client.deployments.ConfigurationMetaNames.FOUNDATION_MODEL: {},
            wml_client.deployments.ConfigurationMetaNames.NAME: name + " " + "deployment",
            wml_client.deployments.ConfigurationMetaNames.BASE_MODEL_ID: model_id
        }
            
        created_deployment = wml_client.deployments.create(asset_id, meta_props)
            
        return wml_client.deployments.get_uid(created_deployment)
    
    @deprecated(
        version="0.6.8",
        reason="'create_prompt_monitor' is deprecated and will be removed in next release, use 'add_prompt_monitor'.",
    )
    def create_prompt_monitor(self,
                              name: str,
                              model_id: str,
                              task_id: Literal["retrieval_augmented_generation", "summarization"],
                              description: str = "",
                              model_parameters: dict = None,
                              prompt_variables: List[str] = None,
                              input_text: str = None,
                              context_fields: List[str] = None,
                              question_field: str = None,
                              ) -> dict:
        """DEPRECATED: use 'add_prompt_monitor'."""
        return self.add_prompt_monitor(name,
                                       model_id,
                                       task_id,
                                       description,
                                       model_parameters,
                                       prompt_variables,
                                       input_text,
                                       context_fields,
                                       question_field) 
        
    def add_prompt_monitor(self,
                              name: str,
                              model_id: str,
                              task_id: Literal["retrieval_augmented_generation", "summarization"],
                              description: str = "",
                              model_parameters: dict = None,
                              prompt_variables: List[str] = None,
                              input_text: str = None,
                              context_fields: List[str] = None,
                              question_field: str = None,
                              ) -> dict:
        """Create an IBM Prompt Template Asset and setup monitors for a given prompt template asset.

        Args:
            name (str): The name of the Prompt Template Asset.
            model_id (str): Id of the model associated with the prompt.
            task_id (str): The task identifier. Currently supports "retrieval_augmented_generation" and "summarization" tasks.
            description (str, optional): Description of the Prompt Template Asset.
            model_parameters (dict, optional): Model parameters and their respective values.
            prompt_variables (List[str], optional): Values for prompt input variables.
            input_text (str, optional): The input text for the prompt.
            context_fields (List[str], optional): A list of fields that will provide context to the prompt. Applicable only for ``retrieval_augmented_generation`` problem type.
            question_field (str, optional): The field containing the question to be answered. Applicable only for ``retrieval_augmented_generation`` problem type.
            
        **Example**

        .. code-block:: python

            watsonx_monitor.create_prompt_monitor(name="IBM prompt template",
                                                    model_id="ibm/granite-3-2b-instruct",
                                                    task_id="retrieval_augmented_generation",
                                                    prompt_variables=["context1", "context2", "input_query"],
                                                    input_text="Prompt text to be given",
                                                    context_fields=["context1", "context2"],
                                                    question_field="input_query")
            
        """
        prompt_metadata = locals()
        # remove unused vars from dict
        prompt_metadata.pop("self", None)
        prompt_metadata.pop("context_fields", None)
        prompt_metadata.pop("question_field", None)
        
        # update name of keys to aigov_facts api
        prompt_metadata["input"] = prompt_metadata.pop("input_text", None)
        
        # update list of vars to dict
        prompt_metadata["prompt_variables"] = { prompt_var: "" for prompt_var in prompt_metadata["prompt_variables"] }
        
        from ibm_cloud_sdk_core.authenticators import IAMAuthenticator  # type: ignore
        from ibm_watson_openscale import APIClient as WosAPIClient  # type: ignore
        
        if not self._wos_client:
            try:
                if hasattr(self, "_wos_cpd_creds") and self._wos_cpd_creds:
                    from ibm_cloud_sdk_core.authenticators import (
                        CloudPakForDataAuthenticator,  # type: ignore
                    )
                    
                    authenticator = CloudPakForDataAuthenticator(**self._wos_cpd_creds)
                    
                    self._wos_client = WosAPIClient(authenticator=authenticator, 
                                                    service_url=self._wos_cpd_creds["url"])
                    
                else:
                    from ibm_cloud_sdk_core.authenticators import (
                        IAMAuthenticator,  # type: ignore
                    )
                    
                    authenticator = IAMAuthenticator(apikey=self._api_key)
                    self._wos_client = WosAPIClient(authenticator=authenticator, service_url=REGIONS_URL[self.region]["wos"])
                    
            except Exception as e:
                logging.error(f"Error connecting to IBM watsonx.governance (openscale): {e}")
                raise
        
        prompt_details = _filter_dict(prompt_metadata, 
                                      ["prompt_variables", "input", "model_parameters"])
        
        asset_details = _filter_dict(prompt_metadata, ["description"],
                                     ["name", "model_id", "task_id"])
        
        pta_id = self._create_prompt_template(prompt_details, asset_details)
        deployment_id = None
        if self._container_type == "space":
            deployment_id =  self._create_deployment_pta(pta_id, name, model_id)
        
        monitors = {
            "generative_ai_quality": {
                "parameters": {
                    "min_sample_size": 10,
                    "metrics_configuration":{}
                    }
                }}
            
        max_attempt_execute_prompt_setup = 0
        while max_attempt_execute_prompt_setup < 2:
            try:
                generative_ai_monitor_details = self._wos_client.wos.execute_prompt_setup(
                    prompt_template_asset_id = pta_id, 
                    space_id = self.space_id,
                    project_id=self.project_id,
                    deployment_id = deployment_id,
                    label_column = "reference_output",
                    context_fields=context_fields,     
                    question_field = question_field,   
                    operational_space_id = self._deployment_stage,
                    problem_type = task_id,
                    input_data_type = "unstructured_text", 
                    supporting_monitors = monitors, 
                    background_mode = False).result
                
                break
                
            except Exception as e:
                if e.code == 403 and "The user entitlement does not exist" in e.message \
                and max_attempt_execute_prompt_setup < 1:
                    max_attempt_execute_prompt_setup = max_attempt_execute_prompt_setup + 1
                    
                    data_marts = self._wos_client.data_marts.list().result
                    if (data_marts.data_marts is None) or (not data_marts.data_marts):
                        raise ValueError("Error retrieving IBM watsonx.governance (openscale) data mart. \
                                         Make sure the data mart are configured.")
                        
                    data_mart_id = data_marts.data_marts[0].metadata.id
                    
                    self._wos_client.wos.add_instance_mapping(
                        service_instance_id=data_mart_id,
                        space_id=self.space_id,
                        project_id=self.project_id)
                else:
                    max_attempt_execute_prompt_setup = 2
                    raise e

        generative_ai_monitor_details = generative_ai_monitor_details._to_dict()
            
        return {"prompt_template_asset_id": pta_id,
                "deployment_id": deployment_id,
                "subscription_id": generative_ai_monitor_details["subscription_id"]} 
    
    @deprecated(
        version="0.6.8",
        reason="'payload_logging' is deprecated and will be removed in next release, use 'store_payload_records'.",
    )
    def payload_logging(self, payload_records: List[dict], subscription_id: str) -> None:
        """DEPRECATED: use 'store_payload_records'."""
        return self.store_payload_records(payload_records, subscription_id)  

    @deprecated(
        version="0.6.11",
        reason="'add_payload_records' is deprecated and will be removed in next release, use 'store_payload_records'.",
    )
    def add_payload_records(self, payload_records: List[dict], subscription_id: str) -> None:
        """DEPRECATED: use 'store_payload_records'."""
        return self.store_payload_records(payload_records, subscription_id)  
                    
    def store_payload_records(
        self, 
        records_request: List[dict], 
        subscription_id: str, 
        payload_records: List[dict] = None
        ) -> List[str]:
        """Store records to payload logging.

        Args:
            records_request (List[dict]): 
            subscription_id (str): 

        **Example**

        .. code-block:: python

            watsonx_monitor.store_payload_records(records_request=[{"context1": "value_context1",
                                                    "context2": "value_context1",
                                                    "input_query": "What's Pineflow?",
                                                    "input_token_count": 25,
                                                    "generated_token_count": 150}], 
                                            subscription_id="5d62977c-a53d-4b6d-bda1-7b79b3b9d1a0")
        """
        # START deprecated params message
        if payload_records is not None:
            warnings.warn(
                "'payload_records' is deprecated and will be removed in a future version. "
                "Please use 'records_request' instead.",
                DeprecationWarning,
                stacklevel=2
            )
            if records_request is None:
                records_request = payload_records
        # END deprecated params message           
        from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
        from ibm_watson_openscale import APIClient as WosAPIClient
        from ibm_watson_openscale.supporting_classes.enums import (
            DataSetTypes,
            TargetTypes,
        )
        
        if not self._wos_client:
            try:
                if hasattr(self, "_wos_cpd_creds") and self._wos_cpd_creds:
                    from ibm_cloud_sdk_core.authenticators import (
                        CloudPakForDataAuthenticator,  # type: ignore
                    )
                    
                    authenticator = CloudPakForDataAuthenticator(**self._wos_cpd_creds)
                    
                    self._wos_client = WosAPIClient(authenticator=authenticator, 
                                                    service_url=self._wos_cpd_creds["url"])
                    
                else:
                    from ibm_cloud_sdk_core.authenticators import (
                        IAMAuthenticator,  # type: ignore
                    )
                    
                    authenticator = IAMAuthenticator(apikey=self._api_key)
                    self._wos_client = WosAPIClient(authenticator=authenticator, service_url=REGIONS_URL[self.region]["wos"])
                
            except Exception as e:
                logging.error(f"Error connecting to IBM watsonx.governance (openscale): {e}")
                raise
        
        subscription_details = self._wos_client.subscriptions.get(subscription_id).result
        subscription_details = json.loads(str(subscription_details))
            
        feature_fields = subscription_details["entity"]["asset_properties"]["feature_fields"]
            
        payload_data_set_id = self._wos_client.data_sets.list(type=DataSetTypes.PAYLOAD_LOGGING,
                                                              target_target_id=subscription_id, 
                                                              target_target_type=TargetTypes.SUBSCRIPTION).result.data_sets[0].metadata.id
            
        payload_data = _convert_payload_format(records_request, feature_fields)
        self._wos_client.data_sets.store_records(data_set_id=payload_data_set_id, 
                                                 request_body=payload_data,
                                                 background_mode=True)
        
        return [data["scoring_id"]+"-1" for data in payload_data]

# DEPRECATED remove in next release
class WatsonxPromptMonitoring(WatsonxPromptMonitor):
    def __init__(self, *args, **kwargs):
        warnings.warn(
            "'WatsonxPromptMonitoring' is deprecated and will be removed. Use 'WatsonxPromptMonitor' instead.",
            DeprecationWarning,
            stacklevel=2
        )
        super().__init__(*args, **kwargs)

# Supporting class
class WatsonxLocalMonitorMetric(BaseModel):
    """Provides watsonx.governance local monitor metric definition.
     
    Args:
        name (str): Name of metric.
        data_type (str): Currently supports "string", "integer", "double", "timestamp".
        nullable (bool):
    """
    
    name: str
    data_type: Literal["string", "integer", "double", "timestamp"]
    nullable: bool = True
    
    def _to_dict(self) -> Dict:        
        return {
            "name": self.name, 
            "type": self.data_type,
            "nullable": self.nullable
            }

# DEPRECATED remove in next release
# Supporting class
class WatsonxTransactionMetric(WatsonxLocalMonitorMetric):
    def __init__(self, *args, **kwargs):
        warnings.warn(
            "'WatsonxTransactionMetric' is deprecated and will be removed. Use 'WatsonxLocalMonitorMetric' instead.",
            DeprecationWarning,
            stacklevel=2
        )
        super().__init__(*args, **kwargs)

# Supporting class        
class WatsonxMonitorMetric(BaseModel):
    """Provides watsonx.governance global monitor metric definition.
     
    Args:
        name (str): Name of metric.
        applies_to (List[str]): Currently supports "summarization", "generation", "question_answering", "extraction" "retrieval_augmented_generation".
    """
    
    name: str
    applies_to: List[Literal["summarization", "generation", "question_answering", "extraction", "retrieval_augmented_generation"]]
    
    def to_dict(self) -> Dict:
        from ibm_watson_openscale.base_classes.watson_open_scale_v2 import (
            ApplicabilitySelection,
        )
        
        return {
            "name": self.name, 
            "applies_to": ApplicabilitySelection(problem_type=self.applies_to) 
            }

# Supporting class
class WatsonxMetricRequest(BaseModel):
    """Initialize a WatsonxMetricRequest object.
     
    Args:
        metrics (List[dict]):  Metrics grouped for a single measurement.
        run_id (str, optional): ID of the monitoring run which produced the measurement.
    """
    
    timestamp: datetime.datetime = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    metrics: List[dict]
    run_id: Optional[str] = None
    
    def __init__(
        self, metrics: List[dict],
        run_id: Optional[str] = None
        ) -> None:
        
        super().__init__(metrics=metrics,
                run_id=run_id)

# DEPRECATED remove in next release
# Supporting class
class WatsonxMeasurementRequest(WatsonxMetricRequest):
    def __init__(self, *args, **kwargs):
        warnings.warn(
            "'WatsonxMeasurementRequest' is deprecated and will be removed. Use 'WatsonxMetricRequest' instead.",
            DeprecationWarning,
            stacklevel=2
        )
        super().__init__(*args, **kwargs)
        
class WatsonxCustomMetric:
    """Provides functionality to setup custom metric to measure your model performance with IBM watsonx.governance.
    
    Args:
        api_key (str): IBM watsonx.governance API key.
        region (str, optional): Region where the watsonx.governance is hosted when using IBM Cloud. Defaults to ``us-south``
        cpd_creds (CloudPakforDataCredentials, optional): Cloud Pak for Data environment details.
    """
    
    def __init__(
        self,
        api_key: str = None,
        region: Literal["us-south", "eu-de", "au-syd"] = "us-south",
        cpd_creds: CloudPakforDataCredentials | dict = None
        ) -> None:
        try:
            from ibm_cloud_sdk_core.authenticators import (
                IAMAuthenticator,  # type: ignore
            )
            from ibm_watson_openscale import APIClient as WosAPIClient  # type: ignore

        except ImportError:
            raise ImportError("""ibm-watson-openscale not found, 
                                please install it with `pip install ibm-watson-openscale`""")

        self.region = region
        self._api_key = api_key
        self._wos_client = None
        
        if cpd_creds: 
            self._wos_cpd_creds = _filter_dict(cpd_creds.to_dict(), ["username", "password", "api_key", 
                                                                   "disable_ssl_verification"], ["url"])
            
        if not self._wos_client:
            try:
                if hasattr(self, "_wos_cpd_creds") and self._wos_cpd_creds:
                    from ibm_cloud_sdk_core.authenticators import (
                        CloudPakForDataAuthenticator,  # type: ignore
                    )
                    
                    authenticator = CloudPakForDataAuthenticator(**self._wos_cpd_creds)
                    
                    self._wos_client = WosAPIClient(authenticator=authenticator, 
                                                    service_url=self._wos_cpd_creds["url"])
                    
                else:
                    from ibm_cloud_sdk_core.authenticators import (
                        IAMAuthenticator,  # type: ignore
                    )
                    
                    authenticator = IAMAuthenticator(apikey=self._api_key)
                    self._wos_client = WosAPIClient(authenticator=authenticator, service_url=REGIONS_URL[self.region]["wos"])
                    
            except Exception as e:
                logging.error(f"Error connecting to IBM watsonx.governance (openscale): {e}")
                raise
            
    def _add_integrated_system(
        self, 
        credentials: IntegratedSystemCredentials,
        name: str, 
        endpoint: str
        ) -> str:
        custom_metrics_integrated_system = self._wos_client.integrated_systems.add(
            name=name,
            description="Integrated system created from Pineflow.",
            type="custom_metrics_provider",
            credentials=credentials.to_dict(),
            connection={
                "display_name": name,
                "endpoint": endpoint
                }
            ).result
        
        return custom_metrics_integrated_system.metadata.id
    
    def _add_monitor_definitions(
        self,
        name: str,
        monitor_metrics: List[WatsonxMonitorMetric],
        schedule: bool
        ):
        from ibm_watson_openscale.base_classes.watson_open_scale_v2 import (
            ApplicabilitySelection,
            MonitorInstanceSchedule,
            MonitorMetricRequest,
            MonitorRuntime,
            ScheduleStartTime,
        )
        
        _monitor_metrics = [MonitorMetricRequest(**metric.to_dict()) for metric in monitor_metrics]
        _monitor_runtime = None
        _monitor_schedule = None
        
        if schedule:
            _monitor_runtime = MonitorRuntime(type="custom_metrics_provider")
            _monitor_schedule = MonitorInstanceSchedule(
                repeat_interval=1,
                repeat_unit="hour", 
                start_time=ScheduleStartTime(type = "relative", delay_unit= "minute", delay = 30))
        
        custom_monitor_details = self._wos_client.monitor_definitions.add(
            name=name, 
            metrics=_monitor_metrics, 
            tags=[], 
            schedule = _monitor_schedule,
            applies_to=ApplicabilitySelection(input_data_type=["unstructured_text"]), 
            monitor_runtime = _monitor_runtime, 
            background_mode=False).result
        
        return custom_monitor_details.metadata.id
    
    def _get_monitor_instance(
        self, 
        subscription_id: str,
        monitor_definition_id: str
        ):
        monitor_instances = self._wos_client.monitor_instances.list(
            monitor_definition_id=monitor_definition_id,
            target_target_id=subscription_id
            ).result.monitor_instances
        
        if len(monitor_instances) == 1:
            return monitor_instances[0]
        else:
            return None
    
    def _update_monitor_instance(
        self, 
        integrated_system_id: str, 
        custom_monitor_id: str
        ):
            payload = [
                {
                    "op": "replace",
                    "path": "/parameters",
                    "value": {
                        "custom_metrics_provider_id": integrated_system_id,
                        "custom_metrics_wait_time": 60,
                        "enable_custom_metric_runs": True
                        }
                    }
                ]
            
            return self._wos_client.monitor_instances.update(
                custom_monitor_id, 
                payload, 
                update_metadata_only = True).result
    
    def _get_patch_request_field(
        self,
        field_path: str, 
        field_value: Any, 
        op_name: str = "replace"
        ) -> Dict:
        return {
            "op": op_name,
            "va": field_path,
            "value": field_value
        }
    
    def _get_dataset_id(
        self,
        subscription_id: str,
        data_set_type: Literal["feedback", "payload_logging"]
        ) -> str:
        data_sets = self._wos_client.data_sets.list(
            target_target_id = subscription_id, 
            type = data_set_type).result.data_sets
        data_set_id = None
        if len(data_sets) > 0:
            data_set_id = data_sets[0].metadata.id
        return data_set_id
    
    def _get_dataset_data(
        self,
        data_set_id: str
        ):
        json_data = self._wos_client.data_sets.get_list_of_records(data_set_id=data_set_id,
                                                                   format="list").result
        
        if not json_data.get("records"):
            return None
        
        return json_data["records"][0]

    def _get_existing_data_mart(self):
        data_marts = self._wos_client.data_marts.list().result.data_marts
        if len(data_marts) == 0:
            raise Exception("No data marts found. Please ensure at least one data mart is available.")
        
        return data_marts[0].metadata.id
    
    # ## Global custom metrics methods
    @deprecated(
        version="0.6.8",
        reason="'create_metric_definition' is deprecated and will be removed in next release, use 'add_metric_definition'.",
    )
    def create_metric_definition(self,
            name: str,
            monitor_metrics: List[WatsonxMonitorMetric],
            integrated_system_url: str,
            integrated_system_credentials: IntegratedSystemCredentials,
            schedule: bool = False):
        return self.add_metric_definition(
            name,
            monitor_metrics,
            integrated_system_url,
            integrated_system_credentials,
            schedule
        )
     
    def add_metric_definition(
        self,
        name: str,
        monitor_metrics: List[WatsonxMonitorMetric],
        integrated_system_url: str,
        integrated_system_credentials: IntegratedSystemCredentials,
        schedule: bool = False
        ):
        """Create custom monitor definition to IBM watsonx.governance.

        This must be done before using custom metrics.
        
        Args:
            name (str): Name of custom metric group.
            monitor_metrics (List[WatsonxMonitorMetric]): List of metrics that will be measured.
            schedule (bool): Enable or disable the scheduler. Defaults to False.
            integrated_system_url (str): URL of external metric.
            integrated_system_credentials (IntegratedSystemCredentials): Integrated system credentials.

        """
        integrated_system_id = self._add_integrated_system(integrated_system_credentials,
                                                           name,
                                                           integrated_system_url)
        
        external_monitor_id = self._add_monitor_definitions(name,
                                                            monitor_metrics,
                                                            schedule)
        
        # Associate the external monitor with the integrated system
        payload = [
            {
                "op": "add",
                "path": "/parameters",
                "value": {
                    "monitor_definition_ids": [ external_monitor_id ]
                    }
                }
            ]

        return self._wos_client.integrated_systems.update(integrated_system_id, payload).result

    def add_monitor_instance(
        self,
        integrated_system_id: str, 
        monitor_definition_id: str,
        subscription_id: str,
        ):
        """Enable a custom monitor for the specified subscription and monitor definition.
        
        Args:
            integrated_system_id (str): 
            monitor_definition_id (str): The Custom Metric monitor instance ID.
            subscription_id (str):
        """
        from ibm_watson_openscale.base_classes.watson_open_scale_v2 import Target
        
        data_marts = self._wos_client.data_marts.list().result.data_marts
        if len(data_marts) == 0:
            raise Exception("No data marts found. Please ensure at least one data mart is available.")
        
        data_mart_id=data_marts[0].metadata.id
        existing_monitor_instance = self._get_monitor_instance(subscription_id, monitor_definition_id)

        if existing_monitor_instance is None:
            target = Target(
                target_type="subscription",
                target_id=subscription_id
            )
            
            parameters = {
                "custom_metrics_provider_id": integrated_system_id,
                "custom_metrics_wait_time":   60,
                "enable_custom_metric_runs": True
                }

            monitor_instance_details = self._wos_client.monitor_instances.create(
                    data_mart_id=data_mart_id,
                    background_mode=False,
                    monitor_definition_id=monitor_definition_id,
                    target=target,
                    parameters=parameters
                    ).result
        else:
            existing_instance_id = existing_monitor_instance.metadata.id
            monitor_instance_details = self._update_monitor_instance(integrated_system_id, existing_instance_id)
            
        return monitor_instance_details

    @deprecated(
        version="0.6.8",
        reason="'publish_measurements' is deprecated and will be removed in next release, use 'publish_metrics'.",
    )
    def publish_measurements(self,
            monitor_instance_id: str,
            monitor_run_id: str,
            measurements_request: List[WatsonxMetricRequest]):
        return self.publish_metrics(monitor_instance_id,
                                     monitor_run_id,
                                     measurements_request
                                     )
    
    @deprecated(
        version="0.6.11",
        reason="'add_measurements' is deprecated and will be removed in next release, use 'publish_metrics'.",
    )
    def add_measurements(self,
            monitor_instance_id: str,
            monitor_run_id: str,
            measurements_request: List[WatsonxMetricRequest]):
        return self.publish_metrics(monitor_instance_id,
                                     monitor_run_id,
                                     measurements_request
                                     )

    def publish_metrics(
        self,
        monitor_instance_id: str,
        monitor_run_id: str,
        records_request: List[WatsonxMetricRequest],
        measurements_request: List[WatsonxMetricRequest], # DEPRECATED remove in next release
        ):
        """Publishes custom metrics for a specific monitor instance.
        
        Args:
            monitor_instance_id (str): Unique monitor instance ID.
            monitor_run_id (str): 
            records_request (List[WatsonxMetricRequest]):
        """
        # START deprecated params message
        if measurements_request is not None:
            warnings.warn(
                "'measurements_request' is deprecated and will be removed in a future version. "
                "Please use 'records_request' instead.",
                DeprecationWarning,
                stacklevel=2
            )
            if records_request is None:
                records_request = measurements_request
        # END deprecated params message
        from ibm_watson_openscale.base_classes.watson_open_scale_v2 import (
            MonitorMeasurementRequest,
            Runs,
        )
        
        for obj in records_request: obj.run_id = monitor_run_id # noqa: E701
        records_request = [MonitorMeasurementRequest(**obj.dict()) for obj in records_request]
        
        self._wos_client.monitor_instances.add_measurements(
            monitor_instance_id=monitor_instance_id,
            monitor_measurement_request=records_request).result        
        
        run = Runs(watson_open_scale=self._wos_client)
        patch_payload = []
        patch_payload.append(self._get_patch_request_field("/status/state", "finished"))
        patch_payload.append(self._get_patch_request_field("/status/completed_at", datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")))
        
        return run.update(monitor_instance_id=monitor_instance_id, monitoring_run_id=monitor_run_id, json_patch_operation=patch_payload).result
    
    # ## Local custom metrics methods (transaction/record level metrics)
    @deprecated(
        version="0.6.12",
        reason="'add_transaction_metric' is deprecated and will be removed in next release, use 'add_local_metric_definition'.",
    )
    def add_transaction_metric(self, name: str, monitor_metrics: List[WatsonxLocalMonitorMetric], subscription_id: str):
        return self.add_metric_definition_local(name, monitor_metrics, subscription_id)

    def add_local_metric_definition(
        self,
        name: str,
        monitor_metrics: List[WatsonxLocalMonitorMetric],
        subscription_id: str
        ):
        """Create custom metric definition to compute metrics at local (transaction) level to IBM watsonx.governance.
        
        Args:
            name (str): Name of custom transaction metric group.
            monitor_metrics (List[WatsonxLocalMonitorMetric]): 
            subscription_id (str): watsonx.governance subscription ID.
        """
        from ibm_watson_openscale.base_classes.watson_open_scale_v2 import (
            LocationTableName,
            SparkStruct,
            SparkStructFieldPrimitive,
            Target,
        )
        target = Target(target_id=subscription_id, target_type="subscription")
        data_mart_id = self._get_existing_data_mart()
        monitor_metrics = [SparkStructFieldPrimitive(**metric._to_dict()) for metric in monitor_metrics]
        
        schema_fields = [
            SparkStructFieldPrimitive(
                name="scoring_id",
                type="string",
                nullable=False,
            ),
            SparkStructFieldPrimitive(
                name="run_id",
                type="string",
                nullable=True,
            ),
            SparkStructFieldPrimitive(
                name="computed_on",
                type="string",
                nullable=False,
            ),
            ]
        
        schema_fields.extend(monitor_metrics)
        
        data_schema = SparkStruct(
            type="struct",
            fields=schema_fields
        )
    
        return self._wos_client.data_sets.add(
            target=target,
            name=name,
            type="custom",
            data_schema=data_schema,
            data_mart_id=data_mart_id,
            location=LocationTableName(table_name=name.lower().replace(" ", "_") + "_" + str(uuid.uuid4())[:8]),
            background_mode=True
       ).result.metadata.id

    @deprecated(
        version="0.6.12",
        reason="'store_metric_records' is deprecated and will be removed in next release, use 'store_payload_records'.",
    )
    def store_metric_records(
        self,
        custom_local_metric_id: str,
        records_request: List[Dict]
        ):
        return self.store_payload_records(custom_local_metric_id, records_request)
    
    def store_payload_records(
        self,
        custom_local_metric_id: str,
        records_request: List[Dict]
        ):
        """Stores custom metrics to payload records (transaction/record level).
        
        Args:
            custom_local_metric_id (str): Unique custom transaction metric ID.
            records_request (List[Dict]): 
        """
        return self._wos_client.data_sets.store_records(
            data_set_id=custom_local_metric_id, 
            request_body=records_request).result

    def list_local_metrics(self, custom_local_metric_id: str):
        return self._get_dataset_data(custom_local_metric_id)