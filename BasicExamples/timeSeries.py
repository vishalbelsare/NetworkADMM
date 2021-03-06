from cvxpy import *
import itertools
from multiprocessing import Pool
import matplotlib.pyplot as plt
from matplotlib import rc
#from base_test import BaseTest
from cvxopt import matrix
from numpy import linalg as LA
import numpy as np
import scipy as sp
#import cvxpy as cp
import unittest
import math
import sys
from cStringIO import StringIO


def solveX(data):
	inputs = int(data[len(data)-1])
	lamb = data[len(data)-2]
	rho = data[len(data)-3]
	x = data[0:inputs]
	a = data[inputs:2*inputs]
	neighs = data[2*inputs:len(data)-3]
	xnew = Variable(inputs,1)
	g = 0.5*square(norm(xnew - a))
	h = 0
	for i in range(len(neighs)/(2*inputs+1)):
		weight = neighs[i*(2*inputs+1)]
		if(weight != 0):
			u = neighs[i*(2*inputs+1)+1:i*(2*inputs+1)+(inputs+1)]
			z = neighs[i*(2*inputs+1)+(inputs+1):(i+1)*(2*inputs+1)]
			h = h + rho/2*square(norm(xnew - z + u))
	objective = Minimize(g+h)
	constraints = []
	p = Problem(objective, constraints)
	result = p.solve()
	if(result == None):
		for i in range(len(neighs)/(2*inputs+1)):
			weight = neighs[i*(2*inputs+1)]
			if(weight != 0):
				u = neighs[i*(2*inputs+1)+1:i*(2*inputs+1)+(inputs+1)]
				z = neighs[i*(2*inputs+1)+(inputs+1):(i+1)*(2*inputs+1)]
				#print u, z
		#print neighs, a
		objective = Minimize(2*g+h)
		p = Problem(objective, constraints)
		result = p.solve()
		print "CVXPY BUG?", p	
	return xnew.value

def solveZ(data):
	#Old method: h = lamb*weight*norm(z1-z2)+rho/2*(square(norm(x1+u1-z1))+square(norm(x2+u2-z2)))
	inputs = int(data[len(data)-1])
	lamb = data[len(data)-2]
	rho = data[len(data)-3]
	x1 = data[0:inputs]
	x2 = data[inputs:2*inputs]
	u1 = data[2*inputs:3*inputs]
	u2 = data[3*inputs:4*inputs]
	weight = data[len(data)-4]
	a = x1 + u1
	b = x2 + u2
	theta = max(1 - lamb*weight/(rho*LA.norm(a - b)), 0.5)
	z1 = theta*a + (1-theta)*b
	z2 = theta*b + (1-theta)*a
	znew = np.matrix(np.concatenate([z1, z2])).reshape(2*inputs,1)
	return znew

def solveU(data):
	leng = len(data)-1
	u = data[0:leng/3]
	x = data[leng/3:2*leng/3]
	z = data[(2*leng/3):leng]
	rho = data[len(data)-1]
	return u + (x - z)

def runADMM_Grid(m, edges, inputs, lamb, rho, numiters, x, u, z, S, ids, a):
	#Find actual solution
	x_actual = Variable(inputs,m)
	g = 0
	for i in range(m):
		g = g + 0.5*square(norm(x_actual[:,i] - a[:,i]))
	f = 0
	for i in range(edges):
		f = f + S.getrow(ids[i,0]).getcol(ids[i,1]).todense()*norm(x_actual[:,ids[i,0]] - x_actual[:,ids[i,1]])
	objective = Minimize(g + lamb*f)
	constraints = []
	p = Problem(objective, constraints)
	result_actual = p.solve()

	#Find max degree of graph
	maxdeg = 0;
	for i in range(m):
		maxdeg = max(maxdeg, len(S.getrow(i).nonzero()[1]))
	iters = 0

	#Stopping criteria
	(s, r, epri, edual) = (1,1,0,0)
	A = np.zeros((2*edges, m))
	for i in range(edges):
		A[2*i,ids[i,0]] = 1
		A[2*i+1, ids[i,1]] = 1
	sqn = math.sqrt(m*inputs)
	sqp = math.sqrt(2*inputs*edges)
	eabs = math.pow(10,-3) #CHANGE THESE TWO AS PARAMS
	erel = math.pow(10,-4)

	maxProcesses =  100
	pool = Pool(processes = min(max(m, edges), maxProcesses))
	#pool = Pool(processes = max(m, edges))
	while(iters < numiters and (r > epri or s > edual or iters < 1)):
		#x update
		neighs = np.zeros(((2*inputs+1)*maxdeg,m))
		for i in range(m):
			counter = 0
			for j in range(edges):
			#Smaller number always first. This is ij with i < j
				if(ids[j,0] == i):
					neighs[counter*(2*inputs+1),i] = S.getrow(i).getcol(ids[j,1]).todense() #weight
					neighs[counter*(2*inputs+1)+1:counter*(2*inputs+1)+(inputs+1),i] = u[:,2*j] #u_ij 
					neighs[counter*(2*inputs+1)+(inputs+1):(counter+1)*(2*inputs+1),i] = z[:,2*j] #z_ij
					counter = counter + 1
				elif(ids[j,1] == i):
					neighs[counter*(2*inputs+1),i] = S.getrow(i).getcol(ids[j,0]).todense()
					neighs[counter*(2*inputs+1)+1:counter*(2*inputs+1)+(inputs+1),i] = u[:,2*j+1]
					neighs[counter*(2*inputs+1)+(inputs+1):(counter+1)*(2*inputs+1),i] = z[:,2*j+1]
					counter = counter + 1
		temp = np.concatenate((x,a,neighs,np.tile([rho,lamb,inputs], (m,1)).transpose()), axis=0)
		newx = pool.map(solveX, temp.transpose())
		x = np.array(newx).transpose()[0]
 
		#z update
		ztemp = z.reshape(2*inputs, edges, order='F')
		utemp = u.reshape(2*inputs, edges, order='F')
		xtemp = np.zeros((inputs, 2*edges))
		weights = np.zeros((1, edges))
		for j in range(edges):
			weights[0,j] = S.getrow(ids[j,0]).getcol(ids[j,1]).todense()
			xtemp[:,2*j] = np.array(x[:,ids[j,0]])
			xtemp[:,2*j+1] = x[:,ids[j,1]]
		xtemp = xtemp.reshape(2*inputs, edges, order='F')
		temp = np.concatenate((xtemp,utemp,ztemp,weights,np.tile([rho,lamb,inputs], (edges,1)).transpose()), axis=0)
		newz = pool.map(solveZ, temp.transpose())
		ztemp = np.array(newz).transpose()[0]
		ztemp = ztemp.reshape(inputs, 2*edges, order='F')
		s = LA.norm(rho*np.dot(A.transpose(),(ztemp - z).transpose())) #For dual residual
		z = ztemp

		#u update
		xtemp = np.zeros((inputs, 2*edges))
		for j in range(edges):
			xtemp[:,2*j] = np.array(x[:,ids[j,0]])
			xtemp[:,2*j+1] = x[:,ids[j,1]]
		temp = np.concatenate((u, xtemp, z, np.tile(rho, (1,2*edges))), axis=0)
		newu = pool.map(solveU, temp.transpose())
		u = np.array(newu).transpose()

		#Stopping criterion - p19 of ADMM paper
		epri = sqp*eabs + erel*max(LA.norm(np.dot(A,x.transpose()), 'fro'), LA.norm(z, 'fro'))
		edual = sqn*eabs + erel*LA.norm(np.dot(A.transpose(),u.transpose()), 'fro')
		r = LA.norm(np.dot(A,x.transpose()) - z.transpose(),'fro')
		s = s #updated at z-step

		obj2 = 0
		for i in range(m):
			obj2 = obj2 + 0.5*(LA.norm(x[:,i] - a[:,i]))*(LA.norm(x[:,i] - a[:,i]))
		obj1 = 0
		for i in range(edges):
			obj1 = obj1 + S.getrow(ids[i,0]).getcol(ids[i,1]).todense()*LA.norm(x[:,ids[i,0]] - x[:,ids[i,1]])
		print lamb*obj1 + obj2 - result_actual, result_actual
		print r, epri, s, edual
		iters = iters + 1

	pool.close()
	pool.join()

	#TO USE ACTUAL SOLUTION
	if(numiters == 0):
		x = np.array(x_actual.value)
	
	(obj2, obj1) = (0, 0)
	for i in range(m):
		obj2 = obj2 + 0.5*(LA.norm(x[:,i] - a[:,i]))*(LA.norm(x[:,i] - a[:,i]))
	for i in range(edges):
		obj1 = obj1 + S.getrow(ids[i,0]).getcol(ids[i,1]).todense()*LA.norm(x[:,ids[i,0]] - x[:,ids[i,1]])
	print lamb*obj1 + obj2 - result_actual, result_actual
	return (x, u, z, x_actual, obj1, obj2)

def main():
	#Build 2x2 Grid
	size = 12
	edges = size - 1
	m = size
	inputs = 10
	rho = 2

	#Uniform weights, build graph
	(weights, ids) = (np.ones((edges,1)).flatten(), np.zeros((edges, 2)).astype(np.int64))
	counter = 0
	for i in range(m-1):
			ids[counter,0] = round(i)
			ids[counter,1] = round(i+1)
			counter = counter + 1
	S = sp.sparse.coo_matrix((weights,(ids[:,0].flatten(),ids[:,1].flatten())), shape=(m,m))
	S = S + S.transpose() #+ sp.sparse.identity(m)

	#Random "targets" a
	np.random.seed(2) #usually seed 0
	a_noise = np.random.randn(inputs, m)
	a = np.zeros((inputs,m))
	#Random
	for i in range(7):
		a[:,i] = a_noise[:,i] + [1,2,3,4,5,6,7,8,9,10]
	for i in range(5):
		a[:,i+7] = a_noise[:,i+7] + [4,3,7,1,2,9,8,10,6,5]
	#For GenCon Solution - see old files
	(x,u,z,counter) = (np.zeros((inputs,m)),np.zeros((inputs,2*edges)),np.zeros((inputs,2*edges)),1)

	numiters = 0
	thresh = 10
	lamb = 7.688671875#0.2
	updateVal = 1.5
	numtrials = math.log(thresh/lamb, updateVal) + 1 
	plots =	np.zeros((math.floor(numtrials)+1,2))
	counter = 1
	#Solve for lambda = 0
	(x, u, z, xSol, pl1, pl2) = runADMM_Grid(m, edges, inputs, 0, 0.00001, numiters, x, u ,z, S, ids, a)
	(U, L) = (x.max(), x.min())
	plt.figure(counter - 1)
	for i in range(inputs):
		plt.plot(np.arange(12), x[i])
	plt.ylim([-2,12])
	plt.xlabel('Month')
	#plots[counter-1,:] = [pl1, pl2]
	#(U, L) = (9, -2.3)
	while(lamb <= thresh):
		print lamb
		(x, u, z, xSol, pl1, pl2) = runADMM_Grid(m, edges, inputs, lamb, rho, numiters, x, u ,z, S, ids, a)
		plt.figure(counter)
		for i in range(inputs):
			plt.plot(np.arange(12), x[i])
		plt.ylim([-2,12])
		plt.xlabel('Month')
		#plots[counter,:] = [pl1, pl2]
		counter = counter + 1
		print lamb
		lamb = lamb*updateVal
	print "Finished"

	#Plot noiseless
	a_noiseless = a - a_noise
	plt.figure(counter).suptitle('Actual Solution')
	for i in range(inputs):
		plt.plot(np.arange(12), a_noiseless[i])
	plt.ylim([-2,12])
	plt.xlabel('Month')

	# plt.figure(counter+1)
	# plt.plot(plots[:,0], plots[:,1], 'ro')
	# plt.xlabel('$\sum w_{jk}||x_j - x_k||$')
	# plt.ylabel('$\sum f_i(x_i)$')	
	#counter = counter + 2
	#REWEIGHTING STEP
	reweight = 1
	lamb = lamb/2
	if (reweight == 1):
		S_temp = S
		(x, u, z, xSol, pl1, pl2) = runADMM_Grid(m, edges, inputs, lamb, rho, numiters, x, u ,z, S, ids, a)
		for i in range(edges):
			val = LA.norm(x[:,ids[i,0]] - x[:,ids[i,1]])
			if(val >= 1e0):
				(S_temp[ids[i,0],ids[i,1]],S_temp[ids[i,1],ids[i,0]]) = (0.0,0.0)
		(x, u, z, xSol, pl1, pl2) = runADMM_Grid(m, edges, inputs, lamb, rho, numiters, x, u ,z, S_temp, ids, a)
		plt.figure(counter+1)
		for i in range(inputs):
			plt.plot(np.arange(12), x[i])
		plt.ylim([-2,12])
		plt.xlabel('Month')

	plt.rc('font', family='serif')
	plt.show()

if __name__ == '__main__':
	main()