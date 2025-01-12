import networkx as nx
import numpy as np
import osmnx as ox

from Manhattan_Graph_Environment.graphs.ManhattanGraph import ManhattanGraph

N_HUBS = 92
myManhattan = ManhattanGraph('simple', N_HUBS)


class LearnGraph:

    def __init__(self, n_hubs: int, manhattan_graph, final_hub):
        self.G = nx.complete_graph(n_hubs, nx.MultiDiGraph)
        self.manhattan_graph = manhattan_graph
        self.final_hub = final_hub
        for node in self.G.nodes():
            self.G.add_edge(node, node)
        self.wait_till_departure_times = {}
        self.list_hubs = self.manhattan_graph.hubs
        # ox.save_graphml(self.G, filepath="./data/graph/learn.graphml")

    def adjacency_matrix(self, layer: str):
        """Returns the adjacency matrix of one of the layers cost, distinction and remaining_distance.

        Args:
            layer (str): Layer to be retrieved as weights of adjacency matrix. Can be "cost", "distinction" or "remaining_distance".Defaults to None.

        Returns:
            np.array: Adjacency matrix with layer values as weights.
        """
        return nx.to_numpy_array(self.G, weight=layer)

    def fill_distance_matrix(self):
        """Uses manhattan_graph to compute distances between all nodes based on travel time shortest path 

        Returns:
            np.array: Distances between all nodes
        """
        distances = np.zeros((N_HUBS, N_HUBS))
        for i in range(N_HUBS):
            for j in range(N_HUBS):
                if (i == j):
                    distances[i, j] = 0
                else:
                    pickup_nodeid = self.manhattan_graph.get_nodeid_by_hub_index(i)
                    dropoff_nodeid = self.manhattan_graph.get_nodeid_by_hub_index(j)
                    path = ox.shortest_path(self.manhattan_graph.inner_graph, pickup_nodeid, dropoff_nodeid,
                                            weight='travel_time')
                    dist_travelled = sum(
                        ox.utils_graph.get_route_edge_attributes(self.manhattan_graph.inner_graph, path,
                                                                 attribute='length'))
                    distances[i, j] = dist_travelled

        return distances

    def add_travel_cost_and_distinction_layer(self, available_trips, distance_matrix):
        """Based on given available shared rides and the prefilled distance matrix, computes travel cost for every 

        Args:
            available_trips (_type_): _description_
            distance_matrix (_type_): _description_
        """
        edges = {}
        edges_distinction = {}

        for k in range(N_HUBS):
            for l in range(N_HUBS):
                if (k == l):
                    edges[(k, l, 0)] = 0
                    edges_distinction[(k, l, 0)] = 0
                    self.wait_till_departure_times[(k, l)] = 0
                # book own ride
                else:
                    edges[(k, l, 0)] = distance_matrix[k, l] * 1
                    edges_distinction[(k, l, 0)] = -1
                    self.wait_till_departure_times[(k, l)] = 300  # 5 minutes for book own ride wait

        for i in range(len(available_trips)):
            for j in range(len(available_trips[i]['route'])):
                if (available_trips[i]['route'][j] in self.list_hubs):
                    pickup_nodeid = available_trips[i]['route'][0]
                    dropoff_nodeid = available_trips[i]['route'][j]

                    pickup_hub_index = self.manhattan_graph.get_hub_index_by_nodeid(pickup_nodeid)
                    dropoff_hub_index = self.manhattan_graph.get_hub_index_by_nodeid(dropoff_nodeid)

                    edges[(pickup_hub_index, dropoff_hub_index, 0)] = distance_matrix[
                                                                          pickup_hub_index, dropoff_hub_index] * 0.1  # share ride is cheaper than book own ride by a factor of 10
                    edges_distinction[(pickup_hub_index, dropoff_hub_index, 0)] = 1
                    self.wait_till_departure_times[(pickup_hub_index, dropoff_hub_index)] = available_trips[i][
                        'departure_time']

        for k in range(N_HUBS):
            for l in range(N_HUBS):
                if (k == l):
                    edges[(k, l, 0)] = 0
                    edges_distinction[(k, l, 0)] = 0
                    self.wait_till_departure_times[(k, l)] = 0

        nx.set_edge_attributes(self.G, edges, "cost")
        nx.set_edge_attributes(self.G, edges_distinction, "distinction")

    def add_remaining_distance_layer(self, current_hub, distance_matrix):
        distance_edges = {}
        dist_current_to_final = distance_matrix[current_hub, self.final_hub]  # get row in distance matrix
        dist_intermediate_to_final = distance_matrix[:, self.final_hub]  # get column of final hub in distance matrix
        distance_gained_array = dist_current_to_final - dist_intermediate_to_final

        for i in range(len(distance_gained_array)):
            distance_edges[(current_hub, i, 0)] = distance_gained_array[i]

        nx.set_edge_attributes(self.G, distance_edges, "remaining_distance")

    def getNearestNodeId(self, pickup_longitude, pickup_latitude):
        pickup_node_id = ox.distance.nearest_nodes(self.G, pickup_longitude, pickup_latitude)
        return pickup_node_id
