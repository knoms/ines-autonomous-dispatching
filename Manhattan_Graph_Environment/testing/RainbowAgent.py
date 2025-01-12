"""
Rainbow Agent.
Is an extended DQN.
"""

import sys
sys.path.insert(0, "")

import os
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')
from ray.rllib.agents.dqn import DQNTrainer, DEFAULT_CONFIG
from config.definitions import ROOT_DIR
from Manhattan_Graph_Environment.gym_graphenv.envs.GraphworldManhattan import GraphEnv, CustomCallbacks

sys.path.append(os.path.join(ROOT_DIR, "Manhattan_Graph_Environment", "gym_graphenv"))


# class definition
class RainbowAgent:
    """
    Init Method of Class
    : param env: Environment Object
    """

    def __init__(self, env):
        sys.path.insert(0, "")
        # Set trainer configuration
        self.trainer_config = DEFAULT_CONFIG.copy()
        self.trainer_config['num_workers'] = 1
        self.trainer_config["train_batch_size"] = 400
        self.trainer_config["gamma"] = 0.99
        # rainbow_config["framework"] = "torch"
        self.trainer_config["callbacks"] = CustomCallbacks
        self.trainer_config["hiddens"] = [180, 150, 100]  # to try with 1024  //was also 516
        self.trainer_config["model"] = {
            # "custom_model": "my_tf_model",
            "fcnet_activation": 'relu',
        }

        # num_gpus and other gpu parameters in order to train with gpu
        # self.trainer_config["num_gpus"] = int(os.environ.get("RLLIB_NUM_GPUS", "0"))

        # rainbow parameters

        # N-step Q learning
        self.trainer_config["n_step"] = 4  # [between 1 and 10]  //was 5 and 7
        # Whether to use noisy network
        self.trainer_config["noisy"] = True
        # rainbow_config["sigma0"] = 0.2
        # Number of atoms for representing the distribution of return. When
        # this is greater than 1, distributional Q-learning is used.
        # the discrete supports are bounded by v_min and v_max
        self.trainer_config["num_atoms"] = 70  # [more than 1] //was 51,20
        self.trainer_config["v_min"] = -15000
        self.trainer_config["v_max"] = 15000  # (set v_min and v_max according to your expected range of returns).

        # here from trainRainbow die config
        # self.trainer_config["train_batch_size"] = 400
        # self.trainer_config["framework"] = "torch"

    """
    Runs the agent in the environment (by taking steps according to policy of agent) until it reaches the final hub.
    :param env: 
    :param reward_list:
    :param env_config:
    :return: dictionary containing results of run.
    """

    def run_one_episode(self, reward_list, env_config):
        # # Initialize trainer
        rainbow_trainer = DQNTrainer(self.trainer_config, GraphEnv)
        # checkpoint anpassen
        file_name = os.path.join(ROOT_DIR, 'tmp', 'rainbow', 'graphworld', 'checkpoint_000081', 'checkpoint-81')
        print(file_name)

        # Restore the Trainer
        rainbow_trainer.restore(file_name)
        # env = gym.make('graphworld-v0')
        env = GraphEnv(use_config=True)
        obs = env.reset()
        print(env.position)
        print("reset done")

        # initialize arrays
        list_nodes = []
        list_hubs = [env.position]
        list_actions = ["start"]
        rem_dist = [env.learn_graph.adjacency_matrix('remaining_distance')[env.position][env.final_hub]]
        # route = [env_config["pickup_hub_index"]]
        # route_timestamps = [datetime.strptime(env_config["pickup_timestamp"], '%Y-%m-%d %H:%M:%S')]
        # sum_reward = 0
        # sum_travel_time = timedelta(seconds=0)
        # print(sum_travel_time)
        # sum_distance = 0
        # results = []
        done = False

        # get information
        route = [env_config["pickup_hub_index"]]
        route_timestamps = [datetime.strptime(env_config["pickup_timestamp"], '%Y-%m-%d %H:%M:%S')]
        sum_reward = 0
        sum_travel_time = timedelta(seconds=0)
        print(sum_travel_time)
        sum_distance = 0
        count_shares = 0
        count_bookowns = 0
        count_wait = 0
        steps = 0
        results = []
        done = False

        # run until finished
        while not done:
            # take some action
            action = rainbow_trainer.compute_action(obs)
            state, reward, done, info = env.step(action)
            sum_reward += reward
            # env.render()
            """
            if done == True:
                print("cumulative reward", sum_reward)
                state = env.reset()
                sum_reward = 0
            """
            if (info["route"][-1] != env.final_hub and info["action"] != "Wait"):
                print(list_nodes)
                list_nodes.extend(info["route"][0:-1])
                print(list_nodes)
            list_hubs.append(info["hub_index"])
            list_actions.append(info["action"])
            rem_dist.append(info["remaining_dist"])

            # get information from action
            route.append(action)
            route_timestamps.append(info.get('timestamp'))

            sum_travel_time += timedelta(seconds=info.get('step_travel_time'))
            delivey_time = datetime.strptime(env_config["delivery_timestamp"], '%Y-%m-%d %H:%M:%S')
            time_until_deadline = timedelta(hours=24) - sum_travel_time
            sum_distance += info.get('distance') / 1000
            number_hubs = info.get('count_hubs')
            dist_shares = info.get("dist_covered_shares")
            dist_bookowns = info.get("dist_covered_bookown")
            # add reward
            sum_reward += reward
            action_choice = info.get("action")

            if action_choice == "Share":
                count_shares += 1
            elif action_choice == "Book":
                count_bookowns += 1
            elif action_choice == "Wait":
                count_wait += 1
            steps += 1

            # check if finished
            if done == True:
                print("DELIVERY DONE!")
                """
                sum_reward: ", sum_reward)
                print("DELIVERY DONE! Route: ", route)
                print("DELIVERY DONE! Travel Time: ", sum_travel_time)
                print("DELIVERY DONE! Distance: ", sum_distance)
                print("DELIVERY DONE! Hubs: ", number_hubs)
                print("DELIVERY DONE! unitl deadline: ", time_until_deadline)
                """
                break

        if count_bookowns == 0:
            ratio = 0
        else:
            ratio = float(count_shares / count_bookowns)
            # print("sum_reward: ",sum_reward)
            # print("sum_reward: ",sum_reward, " time: ",env.time, "deadline time: ", env.deadline, "pickup time: ", env.pickup_time)

        # results of the agent's run
        reward_list = {"pickup_hub": env_config['pickup_hub_index'], "delivery_hub": env_config['delivery_hub_index'],
                       "reward": sum_reward, "hubs": number_hubs, "route": route, "time": sum_travel_time,
                       "dist": sum_distance, "time_until_deadline": time_until_deadline, "timestamps": route_timestamps,
                       "count_bookowns": count_bookowns, "steps": steps, "ratio_share_to_own": ratio,
                       "dist_covered_shares": dist_shares, "dist_covered_bookown": dist_bookowns}

        return reward_list
