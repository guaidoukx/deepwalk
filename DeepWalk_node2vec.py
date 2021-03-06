import os
import matplotlib
from sklearn.manifold import TSNE
import networkx as nx
import numpy as np
import matplotlib.pyplot as plt
from gensim.models import Word2Vec


def extract_ids_labels(file_name):
    ids, labels = [], []
    
    with open(file_name, 'r') as f:
        line = f.readline()
        while line:
            line_splited = line.split()
            ids.append(line_splited[0])
            labels.append(line_splited[-1])
            line = f.readline()
    return ids, labels


def load_graph(filename, ids, direction=False):
    if direction:
        G = nx.DiGraph()
        with open(filename, 'r') as f:
            line = f.readline()
            while line:
                line_splited = line.split()
                if line_splited[0] in ids and line_splited[1] in ids and line_splited[0] != line_splited[1]:
                    G.add_edge(line_splited[0], line_splited[1])
                    G[line_splited[0]][line_splited[1]]['weight'] = 1
                line = f.readline()
    else:
        G = nx.Graph()
        with open(filename, 'r') as f:
            line = f.readline()
            while line:
                line_splited = line.split()
                if line_splited[0] in ids and line_splited[1] in ids and line_splited[0] != line_splited[1]:
                    G.add_edge(line_splited[0], line_splited[1])
                    G[line_splited[0]][line_splited[1]]['weight'] = 1
                    G[line_splited[1]][line_splited[0]]['weight'] = 1
                line = f.readline()
    return G


def alias_setup(probs):
    """
    以图为例，凡是4代表的就是概率类型数的意思
    a，记录下面那些部分的概率值（乘以4以后）
    b，记录上面部分来自哪个根柱子，用哪根柱子的不来用来补足，使之概率为1
    :param probs: 是一个概率的list
    """
    num = len(probs)
    a = np.zeros(num, dtype=np.float32)
    b = np.ones(num, dtype=np.int) * -1  # -1 用来表示，本身自己就足够了，和那些用第一根柱子（下标0）的区分开来
    
    small, large = [], []  # 记录乘以4以后的概率 大于1还是小于1 的下标
    for i, prob in enumerate(probs):
        a[i] = num * prob  # 概率乘以类型数（4）
        if a[i] < 1.0:
            small.append(i)
        else:
            large.append(i)
    
    while len(small) > 0 and len(large) > 0:
        smaller = small.pop()  # 从大小中各任取一个
        larger = large.pop()
        
        a[larger] = a[smaller] + a[larger] - 1.0  # a用来记录本身的概率，而不是加上去的那一部分的概率
        b[smaller] = larger  # b用来记录完成每个柱子=1的操作，补自哪个柱子
        if a[larger] < 1.0:  # 记录大于1的那个概率，给了别人以后，剩下部分是不是还是大于1（是不是还能继续给别人）
            small.append(larger)
        else:
            large.append(larger)
    return a, b


def transition_node_prob_with_one_node(G):
    """
    当只考虑当前节点的时候，也就是只知道一个节点的时候，决定下一个节点往何处。
    :return: 这里考虑的是整个图，形成一个字典。alias_nodes[node] 在当前节点node时，下一步情况的概率情况，也就是 alias 两个数组。
    """
    alias_nodes = {}
    for node in G.nodes():
        probs = [G[node][nbr]['weight'] for nbr in G.neighbors(node)]
        sum_probs = sum(probs)
        normed_probs = [float(prob) / sum_probs for prob in probs]
        alias_nodes[node] = alias_setup(normed_probs)
    return alias_nodes


def transition_node_prob_with_two_nodes(G, direceted, p, q):
    """
    实际上这是在node2vec中的，因为node2vec考虑的不仅是当前节点，而是有两个节点。名字虽然是alias_edges，但是实际上，
    :param p, q: DFS BFS的控制参数
    :return: alias_edges[edge] 反映的还是在当前节点（顺带也要考虑之前的节点），下一步情况的概率情况，是选择节点的 alias 两个数组。
    """
    
    def get_alias_with_two_nodes(G, t, v, p, q):
        """
        :param t: 之前的节点 v，（参考node2vec论文）
        :param v: 当前的节点
        """
        neighbors_of_v = G.neighbors(v)
        weights = []
        for neighbor in neighbors_of_v:
            if neighbor == t:
                weights.append(G[v][neighbor]['weight'] / p)
            elif G.has_edge(neighbor, t):
                weights.append(G[v][neighbor]['weight'])
            else:
                weights.append(G[v][neighbor]['weight'] / q)
        sum_weight = sum(weights)
        norm_weights = [float(weight) / sum_weight for weight in weights]
        return alias_setup(norm_weights)
    
    alias_edges = {}
    if direceted:
        for edge in G.edges():
            alias_edges[edge] = get_alias_with_two_nodes(G, edge[0], edge[1], p, q)
    else:
        for edge in G.edges():
            alias_edges[edge] = get_alias_with_two_nodes(G, edge[0], edge[1], p, q)
            alias_edges[(edge[1], edge[0])] = get_alias_with_two_nodes(G, edge[1], edge[0], p, q)

    return alias_edges


def node2vec_walk(G, start, walk_length, alias_nodes, alias_edges):
    """
    在第一个节点时，只能考虑 一个节点时，下一步情况。在之后，都能考虑 两个节点时，下一步的情况。
    :param alias_nodes， alias_edges: 两个key值不同，代表相同含义的字典。
    :return:
    """
    path = [start]
    while len(path) < walk_length:
        v = path[-1]
        neighbors = list(G.neighbors(v))
        num = len(neighbors)
        if num > 0:
            if len(path) == 1:
                index = int(np.floor(np.random.rand() * num))
                if np.random.rand() < alias_nodes[start][0][index]:
                    path.append(neighbors[index])
                else:
                    path.append(neighbors[alias_nodes[start][1][index]])
            else:
                t = path[-2]
                index = int(np.floor(np.random.rand() * num))
                if np.random.rand() < alias_edges[(t, v)][0][index]:
                    path.append(neighbors[index])
                else:
                    path.append(neighbors[alias_edges[(t, v)][1][index]])
    return path


def node2vec_walks(G, times, walk_length, alias_nodes, alias_edges):
    paths = []
    for node in G.nodes():
        for _ in range(times):
            paths.append(node2vec_walk(G, node, walk_length, alias_nodes, alias_edges))
    return paths


def deepwalk(G, start, walk_length, alias_nodes):
    path = [start]
    node = path[-1]
    neighbours = list(G.neighbors(node))
    num = len(neighbours)
    while len(path) < walk_length and num > 0:
        index = int(np.floor(np.random.rand() * num))
        if np.random.rand() > alias_nodes[node][0][index]:
            cur = neighbours[alias_nodes[node][1][index]]
        else:
            cur = neighbours[index]
        path.append(cur)
        node = cur
        neighbours = list(G.neighbors(node))
        num = len(neighbours)
    return path


def walks(G, times, walk_length, alias_nodes):
    paths = []
    for node in G.nodes():
        for _ in range(times):
            paths.append(deepwalk(G, node, walk_length, alias_nodes))
    return paths


if __name__ == '__main__':

    edge_file_path = 'data/karate/karate.edgelist'
    output_path = 'out/karate/out_paths.txt'
    out_model_path = 'out/karate/model.txt'
    out_graph_path = 'out/karate/graph.png'
    out_embedding_path = 'out/karate/embed.png'
    ids = []
    with open(edge_file_path, 'r') as f:
        line = f.readline()
        while line:
            line_splited = line.split()
            ids.extend([line_splited[0], line_splited[1]])
            line = f.readline()
    
    # 构成图，画图确保图是不是正确的
    G = load_graph(edge_file_path, ids=ids, direction=False)
    plt.plot()
    nx.draw(G, with_labels=True)
    plt.savefig(out_graph_path)
    # plt.show()
    alias_nodes = transition_node_prob_with_one_node(G)
    
    # Option1 [selection of algorithms]-> deepwalk
    # paths = walks(G, 15, 30, alias_nodes)
    
    # Option1 [selection of algorithms]-> node2vec
    p, q, = 0.5, 0.5
    alias_edges = transition_node_prob_with_two_nodes(G, False, p, q)
    paths = node2vec_walks(G, 15, 30, alias_nodes, alias_edges)
    
    with open(output_path, 'w') as f:
        for path in paths:
            sentence = " ".join(path)
            f.write(sentence + '\n')
    print("finish writing")
    
    # Option2 [selections of ways to get 2-dimension]-> embedding to 2dims directly
    word2vec = Word2Vec(paths, size=2, window=3, iter=50)
    vecs = word2vec.wv.vectors
    X, Y = vecs[:, 0], vecs[:, 1]
    
    # Option2 [selections of ways to get 2-dimension]-> embedding to 20dims ，decrease to 2dims with tSNE
    # word2vec = Word2Vec(paths, size=25, window=5, iter=100)
    # vecs = word2vec.wv.vectors
    # tsne = TSNE(n_components=2, learning_rate=1).fit_transform(vecs)
    # X, Y = tsne[:, 0], tsne[:, 1]
    
    vocabs = word2vec.wv.index2word
    
    plt.clf()
    plt.scatter(X, Y, data=vocabs)
    for i, vocab in enumerate(vocabs):
        plt.text(X[i], Y[i], vocab)
    plt.savefig(out_embedding_path)
    # plt.show()
    
    word2vec.save(out_model_path)
    print("finish embedding")
