def neovis_config(crime_no: str):
    return {
        "container_id": "neo4j-graph",
        "server_url": "bolt://localhost:7687",
        "server_user": "neo4j",
        "server_password": "password",

        "labels": {
            "Account": {
                "caption": "account_no",
                "size": "risk_score",
                "community": "accused_account_level",
                "font": {"size": 16},
                "color": {
                    "background": {
                        "property": "accused_account_level",
                        "gradient": {
                            "0": "#2ecc71",   # Victim
                            "1": "#e74c3c",   # L1
                            "2": "#f39c12",   # L2
                            "3": "#3498db"    # L3+
                        }
                    }
                }
            }
        },

        "relationships": {
            "TRANSFERRED_TO": {
                "thickness": "amount",
                "caption": False
            }
        },

        "initial_cypher": f"""
        MATCH (p:Account)-[r:TRANSFERRED_TO]->(c:Account)
        WHERE r.crime_no = '{crime_no}'
        RETURN p,r,c
        """
    }
