"""
This scipt generates random orders that need to delievered for testing the system
and saves them to "random_orders.csv" file in data folder.
The orders are in 2016 as we used taxi trips from this year.     

"""
import csv
import random
import sys
from datetime import datetime, timedelta

import numpy as np

sys.path.insert(0, "")

from Manhattan_Graph_Environment.gym_graphenv.envs.GraphworldManhattan import GraphEnv

env = GraphEnv()

random_orders = []

for i in range(1000):
    final_hub = env.manhattan_graph.get_nodeids_list().index(random.sample(env.hubs, 1)[0])
    start_hub = env.manhattan_graph.get_nodeids_list().index(random.sample(env.hubs, 1)[0])

    # pickup_month =  np.random.randint(5)+1
    pickup_day = np.random.randint(13) + 1
    pickup_hour = np.random.randint(24)
    pickup_minute = np.random.randint(60)

    pickup_time = datetime(2016, 1, pickup_day, pickup_hour, pickup_minute, 0)
    deadline = pickup_time + timedelta(hours=12)

    random_order = {'pickup_node_id': start_hub, 'delivery_node_id': final_hub, 'pickup_timestamp': pickup_time,
                    'delivery_timestamp': deadline}
    random_orders.append(random_order)

field_names = ['pickup_node_id', 'delivery_node_id', 'pickup_timestamp', 'delivery_timestamp']

with open('data/others/random_orders.csv', 'w', newline='') as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=field_names)
    writer.writeheader()
    writer.writerows(random_orders)
