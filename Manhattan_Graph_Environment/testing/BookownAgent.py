"""
Benchmark Agent.
Books 1 own ride from the start to the final hub. Finished.
Methods: run_one_episode
"""

# imports
import sys
sys.path.insert(0,"")
from Manhattan_Graph_Environment.graphs.ManhattanGraph import ManhattanGraph
from Manhattan_Graph_Environment.gym_graphenv.envs.GraphworldManhattan import GraphEnv
import numpy as np
import pandas as pd
import json
import os
import shutil
import gym
import pickle
from datetime import datetime, timedelta
import random
import ray
import warnings
warnings.filterwarnings('ignore')

# class definition
class BookownAgent:
    """
    Runs the agent in the environment (by taking steps according to policy of agent) until it reaches the final hub.
    :param env: 
    :param reward_list:
    :param env_config:
    :return: dictionary containing results of run.
    """
    def run_one_episode (env,reward_list,env_config):
        route = [env_config["pickup_hub_index"]]
        route_timestamps=[]
        env.reset()
        print("reset done")
        print("Delivery Hub",env_config["delivery_hub_index"])
        sum_reward = 0
        sum_travel_time = timedelta(seconds=0)
        print(sum_travel_time)
        sum_distance = 0
        count_shares = 0
        count_bookowns = 0
        count_wait = 0
        steps = 0
        done = False

        # run until finished
        while not done:
            # select final hub as action
            action = env_config["delivery_hub_index"]
            state, reward, done, info = env.step(action)
            done = True
            route.append(action)

            # get information of the action
            print("Timestamps",info.get('timestamp') )
            route_timestamps.append(info.get('timestamp'))
            sum_reward += reward
            sum_travel_time +=timedelta(seconds=info.get('step_travel_time'))
            delivey_time = datetime.strptime(env_config["delivery_timestamp"], '%Y-%m-%d %H:%M:%S')
            time_until_deadline= timedelta(hours=24)-sum_travel_time
            sum_distance += info.get('distance')/1000
            number_hubs=info.get('count_hubs')
            dist_shares = info.get("dist_covered_shares")
            dist_bookowns = info.get("dist_covered_bookown")
            action_choice = info.get("action")

            if action_choice == "Share":
                count_shares += 1
            elif action_choice == "Book":
                count_bookowns += 1
            elif action_choice == "Wait":
                count_wait += 1
            steps += 1

            #env.render()
            if done:
                print("DELIVERY DONE! sum_reward: ",sum_reward)
                print("DELIVERY DONE! Route: ",route)
                print("DELIVERY DONE! Travel Time: ",sum_travel_time)
                print("DELIVERY DONE! Distance: ",sum_distance)
                print("DELIVERY DONE! Hubs: ",number_hubs)
                print("DELIVERY DONE! unitl deadline: ",time_until_deadline)
                break

            # print("sum_reward: ",sum_reward)
            # print("sum_reward: ",sum_reward, " time: ",env.time, "deadline time: ", env.deadline, "pickup time: ", env.pickup_time)
        if count_bookowns == 0:
            ratio = 0
        else:
            ratio = float(count_shares/count_bookowns)

        # results of the agent's run
        reward_list={"pickup_hub":env_config['pickup_hub_index'],"delivery_hub":env_config['delivery_hub_index'],"reward":sum_reward, "hubs":number_hubs, "route":route, "time":sum_travel_time, "dist":sum_distance, "time_until_deadline":time_until_deadline, "timestamps":route_timestamps, "count_bookowns": count_bookowns, "steps": steps, "ratio_share_to_own": ratio,"dist_covered_shares": dist_shares, "dist_covered_bookown": dist_bookowns}
        # print(reward_list)
        return reward_list

    