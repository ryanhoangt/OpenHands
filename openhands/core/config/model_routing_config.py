from dataclasses import dataclass, fields


@dataclass
class ModelRoutingConfig:
    models: list[str] | None = None
    api_key: str | None = None

    def __str__(self):
        attr_str = []
        for f in fields(self):
            attr_name = f.name
            attr_value = getattr(self, f.name)

            attr_str.append(f'{attr_name}={repr(attr_value)}')

        return f"ModelRoutingConfig({', '.join(attr_str)})"

    @classmethod
    def from_dict(cls, model_routing_config_dict: dict) -> 'ModelRoutingConfig':
        return cls(**model_routing_config_dict)

    def __repr__(self):
        return self.__str__()
