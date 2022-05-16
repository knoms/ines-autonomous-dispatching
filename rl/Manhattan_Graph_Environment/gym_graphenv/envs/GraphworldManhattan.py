from xml.dom.pulldom import parseString
import numpy as np
import osmnx as ox
import networkx as nx
import folium
from folium.plugins import MarkerCluster
from datetime import datetime, timedelta
from array import array
import gym
from gym.utils import seeding
import random
import modin.pandas as pd
from gym import spaces
from pandas import Timestamp
import time
import pickle

import sys
sys.path.insert(0,"")

from ManhattanGraph import ManhattanGraph
from LearnGraph import LearnGraph
from OneHotVector import OneHotVector
from database_connection import DBConnection

class GraphEnv(gym.Env):

    REWARD_AWAY = -1
    REWARD_GOAL = 100
    pickup_day = 1
    pickup_hour =  np.random.randint(24)
    pickup_minute = np.random.randint(60) 
    START_TIME = datetime(2016,1,pickup_day,pickup_hour,pickup_minute,0)
    
    def __init__(self, env_config=None):
        """_summary_

        Args:
            graph (nx.MultiDiGraph): graph
            start_hub (int): nodeId
            final_hub (int): nodeId

        """  
        self.LEARNGRAPH_FIRST_INIT_DONE = False
        self.env_config = self.read_config()
        self.n_hubs = 70
        self.distance_matrix = None

        self.DB = DBConnection()

        # Creates an instance of StreetGraph with random trips and hubs
        # graph_meinheim = StreetGraph(filename='meinheim', num_trips=4000, fin_hub=self.final_hub, num_hubs=5)

        manhattan_graph = ManhattanGraph(filename='simple', num_hubs=self.n_hubs)
        #manhattan_graph.setup_trips(self.START_TIME)
        self.manhattan_graph = manhattan_graph

        self.hubs = manhattan_graph.hubs


        self.state = None

      
        self.action_space = gym.spaces.Discrete(self.n_hubs) 
        
        # self.observation_space = spaces.Dict(dict(
        #     #layer_one = spaces.Box(low=0, high=100, shape=(1,self.n_hubs), dtype=np.int32),
        #     cost = gym.spaces.Discrete(self.n_hubs),
        #     current_hub = OneHotVector(self.n_hubs),
        #     final_hub = OneHotVector(self.n_hubs)
        # ))

        # self.observation_space = spaces.Dict(
        #     {'cost': gym.spaces.Discrete(self.n_hubs), 
        #     'current_hub': OneHotVector(self.n_hubs),
        #     'final_hub': OneHotVector(self.n_hubs)}
        # )

        self.observation_space = spaces.Dict(
            {#'cost': gym.spaces.Discrete(self.n_hubs), 
            #'current_hub': OneHotVector(self.n_hubs),
            #'final_hub': OneHotVector(self.n_hubs)
            'cost': gym.spaces.Box(low=np.zeros(70), high=np.zeros(70)+500000, shape=(70,), dtype=np.int64),
            'remaining_distance': gym.spaces.Box(low=np.zeros(70), high=np.zeros(70)+500000, shape=(70,), dtype=np.int64),
            'current_hub': gym.spaces.Box(low=0, high=1, shape=(70,), dtype=np.int64),
            'final_hub': gym.spaces.Box(low=0, high=1, shape=(70,), dtype=np.int64)
            #'current_hub': gym.spaces.Discrete(self.n_hubs),
            #'final_hub': gym.spaces.Discrete(self.n_hubs)
        })

    def one_hot(self, pos):
        one_hot_vector = np.zeros(len(self.hubs))
        one_hot_vector[pos] = 1
        return one_hot_vector

    def reset(self):
        # two cases depending if we have env config 
        #super().reset()

        if (self.env_config == None or self.env_config == {}):
            print("Reset without config")
            #self.final_hub = self.manhattan_graph.get_nodeids_list().index(random.sample(self.hubs,1)[0])
            self.final_hub = random.randint(0,self.n_hubs-1)
            print(f"final hub: {self.final_hub}")
            #self.start_hub = self.manhattan_graph.get_nodeids_list().index(random.sample(self.hubs,1)[0])
            self.start_hub = random.randint(0,self.n_hubs-1)

            # just in case ;)
            if(self.start_hub == self.final_hub):
                self.start_hub = random.randint(0,self.n_hubs-1)

            self.position = self.start_hub
            print(f"current position: {self.position}")

        # time for pickup
            self.pickup_time = self.START_TIME
            self.time = self.pickup_time
            self.total_travel_time = 0
            self.deadline=self.pickup_time+timedelta(hours=12)
            self.current_wait = 1 ## to avoid dividing by 0
            #self.manhattan_graph.setup_trips(self.START_TIME)
        else:
            print("Reset with config")
            self.final_hub = self.env_config['delivery_hub_index']
            print(f"final hub: {self.final_hub}")
            self.start_hub = self.env_config['pickup_hub_index']
            #self.final_hub = self.manhattan_graph.get_node_index_by_hub_index(self.env_config['delivery_hub_index'])
            #self.start_hub = self.manhattan_graph.get_node_index_by_hub_index(self.env_config['pickup_hub_index'])
            self.position = self.start_hub
            print(f"current position: {self.position}")

            self.pickup_time = self.env_config['pickup_timestamp']
            self.time = self.pickup_time
            self.total_travel_time = 0
            self.deadline=self.env_config['delivery_timestamp']
            self.current_wait = 0
            # self.manhattan_graph.setup_trips(self.pickup_time)

        start_timestamp = self.pickup_time - timedelta(hours=2)
        end_timestamp = start_timestamp + timedelta(hours=48)

        self.trips = self.DB.getAvailableTrips(start_timestamp, end_timestamp)
        print("Reset() loaded trips within 48 hrs into memory:", len(self.trips))
        

        learn_graph = LearnGraph(n_hubs=self.n_hubs, manhattan_graph=self.manhattan_graph, final_hub=self.final_hub)
        self.learn_graph = learn_graph

        if(self.LEARNGRAPH_FIRST_INIT_DONE == False):
            self.distance_matrix = self.learn_graph.fill_distance_matrix()

        self.LEARNGRAPH_FIRST_INIT_DONE = True
        self.learn_graph.add_travel_cost_layer(self.availableTrips(), self.distance_matrix)
        self.learn_graph.add_remaining_distance_layer(current_hub=self.position, distance_matrix=self.distance_matrix)

        self.count_hubs = 0
        # old position is current position
        self.old_position = self.start_hub
        # current trip
        self.current_trip = None

        self.own_ride = False
        self.has_waited=False
        reward=0
        #self.available_actions = self.get_available_actions()

        self.state = {
            'cost' : self.learn_graph.adjacency_matrix('cost')[self.position].astype(int),
            'remaining_distance': self.learn_graph.adjacency_matrix('remaining_distance')[self.position].astype(int),
            'current_hub' : self.one_hot(self.position).astype(int), 
            'final_hub' : self.one_hot(self.final_hub).astype(int)
            }
        return self.state

    def step(self, action: int):
        """ Executes an action based on the index passed as a parameter (only works with moves to direct neighbors as of now)

        Args:
            action (int): index of action to be taken from availableActions
        Returns:
            int: new position
            int: new reward 
            boolean: isDone
        """

        startTime = time.time()

        done =  False

        # set old position to current position before changing current position
        self.old_position = self.position
        #availableActions = self.available_actions
        step_duration = 0

        if self.validateAction(action):
            startTimeWait = time.time()
            if(action == self.position):
            # action = wait
                step_duration = 300
                self.has_waited=True
                self.own_ride = False
                print("action == wait ")
                executionTimeWait = (time.time() - startTimeWait)
                print(f"Time Wait: {str(executionTimeWait)}")
                pass

            # action = share ride or book own ride
            else:
                startTimeRide = time.time()
                self.has_waited=False
                self.count_hubs += 1
                #self.own_ride = True                
                # Step Zeit vorrübergehend auskommentiert bis Zeit im State vorhanden ist
                pickup_nodeid = self.manhattan_graph.get_nodeid_by_hub_index(self.position)
                dropoff_nodeid = self.manhattan_graph.get_nodeid_by_hub_index(action)
                # pickup_node_index = self.manhattan_graph.get_index_by_nodeid(pickup_nodeid)
                # dropoff_node_index = self.manhattan_graph.get_index_by_nodeid(dropoff_nodeid)
                route = ox.shortest_path(self.manhattan_graph.inner_graph, pickup_nodeid,  dropoff_nodeid, weight='travel_time')
                route_travel_time = ox.utils_graph.get_route_edge_attributes(self.manhattan_graph.inner_graph,route,attribute='travel_time')

                if(self.learn_graph.wait_till_departure_times[(self.position,action)] == 300):
                    step_duration = sum(route_travel_time)+300 #we add 5 minutes (300 seconds) so the taxi can arrive
                elif(self.learn_graph.wait_till_departure_times[(self.position,action)] != 300 and self.learn_graph.wait_till_departure_times[(self.position,action)] != 0):
                    step_duration = sum(route_travel_time)
                    # TODO: String conversion von departure time besser direkt beim erstellen der Matrix
                    departure_time = datetime.strptime(self.learn_graph.wait_till_departure_times[(self.position,action)], '%Y-%m-%d %H:%M:%S')
                    self.current_wait = ( departure_time - self.time).seconds
                    step_duration += self.current_wait
                    self.time = departure_time
                
                self.old_position = self.position
                self.position = action
                
                
                # Increase global time state by the time waited for the taxi to arrive at our location
                # self.current_wait = (selected_trip['departure_time']-self.time).seconds
                # self.time = selected_trip['departure_time']

                # Instead of cumulating trip duration here we add travel_time 
                # self.total_travel_time += timedelta(seconds=travel_time)     
                # refresh travel cost layer after each step
                # self.learn_graph.add_travel_cost_layer(self.availableTrips())
                # self.state = {'cost' : self.learn_graph.adjacency_matrix('cost')[self.position].astype(int),'current_hub' : self.one_hot(self.position).astype(int), 'final_hub' : self.one_hot(self.final_hub).astype(int)}
                executionTimeRide = (time.time() - startTimeRide)
                print(f"Time Ride: {str(executionTimeRide)}")
                pass 
        else:
            print("invalid action")
            #print("avail actions: ",self.available_actions)
            print("action: ",action)
            print("action space: ",self.action_space)

        
        # refresh travel cost layer after each step
        self.learn_graph.add_travel_cost_layer(self.availableTrips(), self.distance_matrix)
        startTimeLearn = time.time()
        self.state = {'cost' : self.learn_graph.adjacency_matrix('cost')[self.position].astype(int),'remaining_distance': self.learn_graph.adjacency_matrix('remaining_distance')[self.position].astype(int),'current_hub' : self.one_hot(self.position).astype(int), 'final_hub' : self.one_hot(self.final_hub).astype(int)}
        executionTimeLearn = (time.time() - startTimeLearn)
        # print(f"Time Adj Matrix: {str(executionTimeLearn)}")

        self.time += timedelta(seconds=step_duration)

        reward, done = self.compute_reward(action)

        executionTime = (time.time() - startTime)
        # print('Step() Execution time: ' + str(executionTime) + ' seconds')

        return self.state, reward,  done, {}

    
    def compute_reward(self, action):
        cost_of_action = self.learn_graph.adjacency_matrix('cost')[self.old_position][action]
        print(self.old_position, "->", action, cost_of_action)
        if (self.position == self.final_hub and self.time <= self.deadline):
            print("DELIVERED IN TIME")
            reward = 1000
            reward -= cost_of_action
            done = True
        elif(self.position == self.final_hub and self.time > self.deadline):
            overtime = self.time-self.deadline
            print(f"DELIVERED WITH DELAY: {overtime}")
            overtime = round(overtime.total_seconds()/60)
            reward = 1000 - overtime
            reward -= cost_of_action
            done = True
        else:
            reward = -(cost_of_action)
            done = False

        # TODO: include time!

        return reward, done
        
    
    # def compute_reward(self, done):
    #     """ Computes the reward for each step
    #     Args:
    #         bool: own_ride
    #     Returns:
    #         int: reward
    #         bool: done
    #     """
    #     startTime = time.time()

    #     # define weights for reward components
    #     # for the start: every component has the same weight
    #     num_comp = 6
    #     w = 1/num_comp
    #     # later: every component individually
    #     # w1 = ?, w2 = ?, ...

    #     reward = 0
    #     # if we reach the final hub
    #     if (self.position == self.final_hub):
    #         reward += self.REWARD_GOAL
    #         # if the agent books an own ride, penalize reward by 50
    #         #if self.own_ride:
    #         #    reward -= 80
    #         # if the box is not delivered in time, penalize reward by 1 for every minute over deadline
    #         #if (self.time > self.deadline):
    #         #    overtime = self.time-self.deadline
    #         #    overtime = round(overtime.total_seconds()/60)
    #         #    reward -= overtime
    #         done = True

    #     # if we do not reach the final hub, reward is -1
    #     else:
    #         # old reward: reward = self.REWARD_AWAY
    #         # 

    #         # if action was own ride
    #         if self.own_ride:
    #              # punishment is the price for own ride and the emission costs for the distance
    #             path_travelled = ox.shortest_path(self.manhattan_graph.inner_graph, self.manhattan_graph.get_nodeids_list()[self.old_position],  self.manhattan_graph.get_nodeids_list()[self.position], weight='travel_time')
    #             dist_travelled_list = ox.utils_graph.get_route_edge_attributes(self.manhattan_graph.inner_graph,path_travelled,attribute='length')
    #             part_length = sum(dist_travelled_list)
    #             dist_travelled = 1000/part_length
    #             # choose random mobility provider (hereby modelling random availability for an own ride) and calculate trip costs
    #             providers = pd.read_csv("Provider.csv")
    #             id = random.randint(0,len(providers.index))
    #             price = providers['basic_cost'][id] + dist_travelled/1000 * providers['cost_per_km'][id]
    #             reward += dist_travelled - price

    #         # if action was wait
    #         elif (self.has_waited):
    #             # punishment is the time wasted on waiting relative to overall time that is available
    #             if self.time > self.deadline:
    #                 reward = self.deadline - self.time
    #             else:
    #                 reward -= 300/((self.deadline-self.pickup_time).total_seconds())

    #         # if action was to share ride
    #         else:
    #             df_id = self.current_trip['trip_row_id']
    #             # maximize difference between time constraint and relative travelled time
    #             time_diff = (self.deadline - self.time).seconds

    #             # minimize route distance travelled (calculate length of current (part-)trip and divide by total length of respective trip from dataframe)
    #             path_travelled = ox.shortest_path(self.manhattan_graph.inner_graph, self.manhattan_graph.get_nodeids_list()[self.old_position],  self.manhattan_graph.get_nodeids_list()[self.position], weight='travel_time')
    #             dist_travelled_list = ox.utils_graph.get_route_edge_attributes(self.manhattan_graph.inner_graph,path_travelled,attribute='length')
    #             part_length = sum(dist_travelled_list)
    #             dist_travelled = 1000/part_length

    #             # minimize distance to final hub (calculate difference between distance to final hub from the old position and the new position)
    #             oldpath_to_final = ox.shortest_path(self.manhattan_graph.inner_graph, self.manhattan_graph.get_nodeids_list()[self.old_position],  self.manhattan_graph.get_nodeids_list()[self.final_hub], weight='travel_time')
    #             newpath_to_final = ox.shortest_path(self.manhattan_graph.inner_graph, self.manhattan_graph.get_nodeids_list()[self.position],  self.manhattan_graph.get_nodeids_list()[self.final_hub], weight='travel_time')
    #             olddist_tofinal = sum(ox.utils_graph.get_route_edge_attributes(self.manhattan_graph.inner_graph,oldpath_to_final,attribute='length'))
    #             newdist_tofinal = sum(ox.utils_graph.get_route_edge_attributes(self.manhattan_graph.inner_graph,newpath_to_final,attribute='length'))
    #             dist_gained = olddist_tofinal - newdist_tofinal

    #             # minimize number of hops
    #             hops = -self.count_hubs

    #             # minimize waiting time (time between choosing ride and being picked up) 
    #             wait_time = 1/self.current_wait

    #             # minimize costs
    #             # get total route length
    #             total_length = self.manhattan_graph.trips['route_length'][df_id]
    #             # get part route length: access variable part_length
    #             # calculate proportion
    #             prop = part_length/total_length
    #             # calculate price for this route part
    #             price = self.manhattan_graph.trips['total_price'][df_id]*prop
    #             # if path length in dataframe is the same as path length of current trip -> get total costs, otherwise calculate partly costs

    #             passenger_num = self.manhattan_graph.trips['passenger_count'][df_id]
    #             cost = -price/(passenger_num+1)
    #             # in the case of multiagent: cost = price(passenger_num+box_num+1)

    #             # add all to reward
    #             reward += w * time_diff + w * dist_travelled + w * dist_gained + w * hops + w * wait_time + w * cost
    #             # later: take into account each individual weight
    #             # reward += w1 * time_diff + w2 * dist + w3 * hops + w4 * wait_time + w5 * cost

    #     executionTime = (time.time() - startTime)
    #     print('Compute_reward() Execution time: ' + str(executionTime) + ' seconds')
    #     return reward, done



    def get_available_actions(self):
        """ Returns the available actions at the current position. Uses a simplified action space with moves to all direct neighbors allowed.

        Returns:
            list: list of nodeIds of direct neighbors
        """

        startTime = time.time()

        wait = [{'type': 'wait'}]
        ownRide = [{'type': 'ownRide'}]
        available_rides = list(self.availableTrips(10))
        
        executionTime = (time.time() - startTime)
        print('get_available_actions() Execution time: ' + str(executionTime) + ' seconds')

        available_actions = [wait,ownRide,*available_rides]
        self.available_actions = available_actions
        return available_actions

    
    # def availableTrips(self, time_window=5):
    #     Returns a list of all available trips at the current node and within the next 5 minutes. Includes the time of departure from the current node as well as the target node of the trip.

    #     Returns:
    #         list: [departure_time,target_node]
        
    #     list_trips=[]
    #     position=self.manhattan_graph.get_nodeid_by_index(self.position)
    #     position_str=str(position)
    #     final_hub_postion=self.manhattan_graph.get_nodeid_by_index(self.final_hub)

    #     start_timestamp=self.time
    #     end_timestamp = self.time + timedelta(minutes=time_window)

    #     grid=self.manhattan_graph.trips
    #     paths=grid['route_timestamps']
        
    #     row_id = -1
    #     for index in range(len(paths)):
    #         row_id += 1
    #         dict_route = grid['route_timestamps'][index]
    #         dict_route= eval(dict_route)
    #         for tupel_position in dict_route:
    #             startsInCurrentPosition = str(tupel_position) == position_str
    #             if(startsInCurrentPosition):
    #                 position_timestamp= datetime.strptime(str(dict_route[tupel_position]), "%Y-%m-%d %H:%M:%S")
    #                 inTimeframe = start_timestamp <= position_timestamp and end_timestamp >= position_timestamp
    #                 if inTimeframe:
    #                     trip_target_node = grid['dropoff_node'][index]
    #                     isNotFinalNode = str(tupel_position) != str(trip_target_node)
    #                     if(isNotFinalNode):
    #                         string_split = grid['route'][index].replace('[','').replace(']','').split(',')
    #                         route = [int(el) for el in string_split]
    #                         index_in_route = route.index(position)
    #                         route_to_target_node=route[index_in_route::]
    #                         hubsOnRoute = any(node in route_to_target_node for node in self.hubs)
    #                         if hubsOnRoute:
    #                             list_hubs = [node for node in self.hubs if node in route_to_target_node]
    #                             hubs_dict = dict((node, dict_route[node]) for node in list_hubs)
    #                             for hub in hubs_dict:
    #                                 index_hub_in_route = route.index(hub)
    #                                 index_hub_in_route += 1
    #                                 route_to_target_hub = route[index_in_route:index_hub_in_route]
    #                                 if(hub != position):
    #                                     trip = {'departure_time': position_timestamp, 'target_hub': hub, 'route': route_to_target_hub, 'trip_row_id': index}
    #                                     list_trips.append(trip)
    #     self.available_actions = list_trips
    #     print(list_trips)
    #     return list_trips
    
    def availableTrips(self, time_window=5):
        """ Returns a list of all available trips at the current node and within the next 5 minutes. Includes the time of departure from the current node as well as the target node of the trip.

        Returns:
            list: [departure_time,target_node]
        """
        startTime = time.time()
        list_trips=[]
        position=self.manhattan_graph.get_nodeid_by_hub_index(self.position)
        position_str=str(position)
        final_hub_postion=self.manhattan_graph.get_nodeid_by_index(self.final_hub)

        start_timestamp=self.time
        end_timestamp = self.time + timedelta(minutes=time_window)
        
        #list of trip id's that are in current position in that timewindow
        trips = self.trips
        # print("Trips about to be filtered:")
        # print(trips)
        for tripId, nodeId, timestamp in trips:
            if(nodeId == position):
                if timestamp <= end_timestamp and timestamp >= start_timestamp:
            
                    #trip_target_node = grid['dropoff_node'][index]
                    #isNotFinalNode = str(tupel_position) != str(trip_target_node)

                    route, times = self.DB.getRouteFromTrip(tripId)
                    isNotFinalNode = True
                    if isNotFinalNode:
                        print(route)
                        print(nodeId)
                        print(position)
                        print(tripId)
                        index_in_route = route.index(position)
                        position_timestamp = times[index_in_route]
                        route_to_target_node=route[index_in_route::]
                        hubsOnRoute = any(node in route_to_target_node for node in self.hubs)
                        if hubsOnRoute:
                            route_hubs = [node for node in route_to_target_node if node in self.hubs]
                            for hub in route_hubs:
                                index_hub_in_route = route.index(hub)
                                index_hub_in_route += 1
                                route_to_target_hub = route[index_in_route:index_hub_in_route]
                                if(hub != position):
                                    trip = {'departure_time': position_timestamp, 'target_hub': hub, 'route': route_to_target_hub, 'trip_row_id': tripId}
                                    list_trips.append(trip)
        self.available_actions = list_trips

        executionTime = (time.time() - startTime)
        print('in_step_available_trips() Execution time: ' + str(executionTime) + ' seconds')
        print('Available rides for share found in step:', len(list_trips))
        return list_trips

    def validateAction(self, action):
        return action < self.n_hubs

    def read_config(self):
        with open('/Users/noah/Desktop/Repositories/ines-autonomous-dispatching/rl/Manhattan_Graph_Environment/env_config.pkl', 'rb') as f:
            loaded_dict = pickle.load(f)
        self.env_config = loaded_dict
        return loaded_dict
        

    def render(self, visualize_actionspace: bool = False):
        """_summary_

        Args:
            visualize_actionspace (bool, optional): _description_. Defaults to False.

        Returns:
            _type_: _description_
        """
        current_pos_x = self.manhattan_graph.get_node_by_index(self.position)['x']
        current_pos_y = self.manhattan_graph.get_node_by_index(self.position)['y']
        final_hub_x = self.manhattan_graph.get_node_by_index(self.final_hub)['x']
        final_hub_y = self.manhattan_graph.get_node_by_index(self.final_hub)['y']
        start_hub_x = self.manhattan_graph.get_node_by_index(self.start_hub)['x']
        start_hub_y = self.manhattan_graph.get_node_by_index(self.start_hub)['y']
        
        # current_pos_x = list(self.manhattan_graph.nodes())[self.position]['x']
        # current_pos_y = list(self.manhattan_graph.nodes())[self.position]['y']
        # final_hub_x = list(self.manhattan_graph.nodes())[self.final_hub]['x']
        # final_hub_y = list(self.manhattan_graph.nodes())[self.final_hub]['y']
        # start_hub_x = list(self.manhattan_graph.nodes())[self.start_hub]['x']
        # start_hub_y = list(self.manhattan_graph.nodes())[self.start_hub]['y']
        
        # Create plot
        plot = ox.plot_graph_folium(self.manhattan_graph.inner_graph,fit_bounds=True, weight=2, color="#333333")


        #Place markers for the random hubs
        for hub in self.hubs:
            hub_node = self.manhattan_graph.get_node_by_nodeid(hub)
            hub_pos_x = hub_node['x']
            hub_pos_y = hub_node['y']
            popup = "HUB %d" % (hub)
            folium.Marker(location=[hub_pos_y, hub_pos_x],popup=popup, icon=folium.Icon(color='orange', prefix='fa', icon='cube')).add_to(plot)

        # Place markers for start, final and current position
        folium.Marker(location=[final_hub_y, final_hub_x], icon=folium.Icon(color='red', prefix='fa', icon='flag-checkered')).add_to(plot)
        folium.Marker(location=[start_hub_y, start_hub_x], popup = f"Pickup time: {self.pickup_time.strftime('%m/%d/%Y, %H:%M:%S')}", icon=folium.Icon(color='lightblue', prefix='fa', icon='caret-right')).add_to(plot)
        folium.Marker(location=[current_pos_y, current_pos_x], popup = f"Current time: {self.time.strftime('%m/%d/%Y, %H:%M:%S')}", icon=folium.Icon(color='lightgreen', prefix='fa',icon='cube')).add_to(plot)
        

        if(visualize_actionspace):
            for i, trip in enumerate(self.availableTrips()):
                target_hub=self.manhattan_graph.get_node_by_nodeid(trip['target_hub'])
                target_node_x = target_hub['x']
                target_node_y = target_hub['y']
                popup = "%s: go to node %d" % (i, trip['target_hub'])
                folium.Marker(location=[target_node_y, target_node_x], popup = popup, tooltip=str(i)).add_to(plot)
                ox.plot_route_folium(G=self.manhattan_graph.inner_graph,route=trip['route'],route_map=plot)
        # Plot
        # pos_to_final = nx.shortest_path(self.manhattan_graph.inner_graph, self.manhattan_graph.get_nodeid_by_index(self.start_hub), self.manhattan_graph.get_nodeid_by_index(self.final_hub), weight="travel_time")
        # if(not len(pos_to_final)< 2):

        return plot

