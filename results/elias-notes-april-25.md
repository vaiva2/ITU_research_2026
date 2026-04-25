

# Hashtriemap

## Problem:
The hash trie map appears to have a relatively degraded performance on the rpi compared to the DGX spark machine. Here are some thoughts on why that could be.

- Hashtriemaps immutable datastrucure enable CAS operations in order to keep a lock free operation. However this comes with a trade off. To have every object in the hash tree immutable every mutation requires a reallocation of the existing data + the nessecary change (insert or deletion of a key-value pair). This creates a pressure from javas GC as it has to clean up the old objects. For a many core system like the DGX spark, this amortises to a negligable efficiency penalty, and for the RPI it means that all of its 4 cores has to pause executing the hashtriemap in order for the GC to do its work. The difference of the two machine cache also comes into play here. Since the Hashtriemap it is a tree of pointers, a small cache means that following pointers will result in more cache misses on the RPI than the DGX. This comes into play not only for executing the Hashmap, but also when the GC need to collect the massive amount of garbage that the map produces. The object of the hashmap might have a tendency the fragment over a larger span of memory resulting in even more cache misses as the Hashmap executes and need new space for every mutation. This is highly depending on how to GC manages collecting old memory and makes the freed up space available again. In any case these factors hit the rpi much harder than the HPC. Another factor is also the memory band with for reading and writing to memory. the rpi has 17 GB/s bandwidth shared by four cores while the DGX spark machine has about 270 GB/s across some 20 cores. The penalty for chasing pointers is much lower. The CPUs also have different abilities to have pending memory load running in parallel, which also further could be a part of the explanation as to why the hashtriemap performs very well of the DGX spark machine and not on the RPI.

# Caches of the two machines
|Cache       | RPi 5 (Cortex-A76 ×4)DGX | Spark (X925 ×10 + A725 ×10) |
|:---------- |:-------------------------|:----------------------------|
|L2 per core | 512 KB                   | 1.25 MB                     |
|L3 total    | 2 MB                     | 24 MB                       |

# Notes on veryfication of the hypothesis.
We should try and veryfy these claims: 
 - See how much the GC affects performance on the two machine.
 - Look at the cache misses of the machine.
 - Maybe look at the memory bandwidth utilitation some how?

# Some questions:
 - Does the whole cache get evicted with the GC runs? Is there a difference here between the two machines?
 - How much of the cache is evicted for simply one memory load of pointer chasing? and what parameters could affect how much of the cache is evicted?
 - Are lockfree hashmaps inherently bad for machines with fewer cores or are there other lockfree implementations we could try out that show a different trend?

 # Suggestions of other lockfree implementations
 - Cliff Click's NonBlockingHashMap / JCTools NonBlockingHashMap: 
    This hashmap is implementated via one giant array. Everywrite mutate a cell using CAS, and doesn't requires any reallocation except when the array grows and has to resize.
    It could create hot key contention when running a zipfian distrubution of read/writes -> pontentially many CAS retries.
 -  Split ordered linked lists
    A giant linked list of immutable nodes and an array of shortcuts into the list. Uses CAS to replace nodes. Avoids rebuilding the tree and reallocation biggers parts of the tree. There is still a big load on the cache through pointer chasing through the tree.
 - Changing the width of the Cnode array from 6 to 4 (or maybe even 2?). This result in a taller tree, but every allocation takes less memory (16 slots instead of 64) which might perform better on the RPI. NOTE: why?
